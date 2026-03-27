"""Wavelength path tracing algorithm.

Discovers end-to-end wavelength paths by following cable connections
between WDM nodes, traversing through intermediate devices (patch panels, EDFAs).
"""

from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import WdmChannel, WdmLinePort, WdmWavelengthPath, WdmWavelengthPathChannel


def _follow_cable_from_rearport(rear_port):
    """Follow a cable from a rear port to its paired far-end rear port.

    Handles multi-termination trunk cables by matching position in the ordered
    termination list (first A-side maps to first B-side, etc).

    Returns the far-end RearPort or None.
    """
    fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=rear_port.pk)
    if not fresh_rp.cable_id:
        return None

    rp_ct = ContentType.objects.get_for_model(RearPort)

    # Get all terminations for this cable, ordered by PK (creation order = position)
    all_terms = list(
        CableTermination.objects.filter(cable_id=fresh_rp.cable_id, termination_type=rp_ct).order_by("cable_end", "pk")
    )

    # Find which side and position our rear port is on
    my_side = None
    my_index = -1
    a_terms = [t for t in all_terms if t.cable_end == "A"]
    b_terms = [t for t in all_terms if t.cable_end == "B"]

    for i, t in enumerate(a_terms):
        if t.termination_id == fresh_rp.pk:
            my_side = "A"
            my_index = i
            break

    if my_side is None:
        for i, t in enumerate(b_terms):
            if t.termination_id == fresh_rp.pk:
                my_side = "B"
                my_index = i
                break

    if my_side is None or my_index < 0:
        return None

    # Map to the corresponding position on the other side
    far_terms = b_terms if my_side == "A" else a_terms
    if my_index >= len(far_terms):
        return None

    far_term = far_terms[my_index]
    try:
        return RearPort.objects.get(pk=far_term.termination_id)
    except RearPort.DoesNotExist:
        return None


def _follow_frontport_cable(front_port):
    """Follow a cable from a front port to its paired far-end front port.

    Handles multi-termination cables by matching position.
    Returns the far-end FrontPort or None.
    """
    if not front_port.cable_id:
        return None

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    all_terms = list(
        CableTermination.objects.filter(cable_id=front_port.cable_id, termination_type=fp_ct).order_by(
            "cable_end", "pk"
        )
    )

    a_terms = [t for t in all_terms if t.cable_end == "A"]
    b_terms = [t for t in all_terms if t.cable_end == "B"]

    my_side = None
    my_index = -1
    for i, t in enumerate(a_terms):
        if t.termination_id == front_port.pk:
            my_side = "A"
            my_index = i
            break
    if my_side is None:
        for i, t in enumerate(b_terms):
            if t.termination_id == front_port.pk:
                my_side = "B"
                my_index = i
                break

    if my_side is None or my_index < 0:
        return None

    far_terms = b_terms if my_side == "A" else a_terms
    if my_index >= len(far_terms):
        return None

    try:
        return FrontPort.objects.select_related("device").get(pk=far_terms[my_index].termination_id)
    except FrontPort.DoesNotExist:
        return None


def _get_far_end_node(rear_port):
    """Follow cables from rear_port through intermediate devices until reaching a WDM node.

    Pass-through path: RearPort →(cable)→ RearPort →(PortMapping)→ FrontPort →(cable)→ FrontPort →(PortMapping)→ RearPort → ...

    Returns (WdmNode, far_end_RearPort) or (None, None).
    """
    visited = {rear_port.pk}
    current_rp = rear_port

    for _ in range(20):  # max hops to prevent infinite loops
        # Step 1: Follow cable from rear port to far-end rear port
        far_rp = _follow_cable_from_rearport(current_rp)
        if far_rp is None or far_rp.pk in visited:
            return None, None
        visited.add(far_rp.pk)

        # Step 2: Check if this rear port belongs to a WDM node
        try:
            lp = WdmLinePort.objects.select_related("wdm_node").get(rear_port=far_rp)
            return lp.wdm_node, far_rp
        except WdmLinePort.DoesNotExist:
            pass

        # Step 3: Pass through device via PortMapping → FrontPort → cable → FrontPort → PortMapping → RearPort
        pm = PortMapping.objects.filter(rear_port=far_rp).select_related("front_port").first()
        if pm is None:
            return None, None

        source_fp = pm.front_port
        if not source_fp.cable_id:
            return None, None

        # Follow the front port cable to far-end front port
        far_fp = _follow_frontport_cable(source_fp)
        if far_fp is None:
            return None, None

        # Find the rear port on the far-end front port's device via PortMapping
        far_pm = PortMapping.objects.filter(front_port=far_fp).select_related("rear_port").first()
        if far_pm is None or far_pm.rear_port.pk in visited:
            return None, None

        current_rp = far_pm.rear_port
        visited.add(current_rp.pk)

    return None, None


def _get_tx_rear_port(node):
    """Get the TX or BIDI line port's rear port for outbound tracing."""
    from .choices import WdmLineRoleChoices

    lp = (
        WdmLinePort.objects.filter(wdm_node=node, role__in=[WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI])
        .select_related("rear_port")
        .first()
    )
    return lp.rear_port if lp else None


def _get_rx_rear_port(node):
    """Get the RX or BIDI line port's rear port for inbound tracing."""
    from .choices import WdmLineRoleChoices

    lp = (
        WdmLinePort.objects.filter(wdm_node=node, role__in=[WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI])
        .select_related("rear_port")
        .first()
    )
    return lp.rear_port if lp else None


def _find_origin(node, grid_position):
    """Walk backwards via RX ports to find the origin node for a grid position.

    Only considers a node as a predecessor if its TX port connects to
    the current node's RX port (i.e., a forward-direction link).
    """
    visited = {node.pk}
    current = node

    while True:
        rx_rp = _get_rx_rear_port(current)
        if rx_rp is None:
            return current

        prev_node, far_rp = _get_far_end_node(rx_rp)
        if prev_node is None or prev_node.pk in visited:
            return current

        # Verify the far-end rear port is actually a TX port (forward direction)
        tx_rp = _get_tx_rear_port(prev_node)
        if tx_rp is None or far_rp.pk != tx_rp.pk:
            return current  # Not a forward link — this node is the origin

        if not WdmChannel.objects.filter(wdm_node=prev_node, grid_position=grid_position).exists():
            return current

        visited.add(prev_node.pk)
        current = prev_node


def trace_wavelength_path(start_channel):
    """Trace a wavelength path starting from a channel.

    Returns dict with:
        channels: list of WdmChannel in path order
        is_complete: bool
        is_active: bool
    """
    from dcim.models import Cable

    grid_position = start_channel.grid_position
    origin = _find_origin(start_channel.wdm_node, grid_position)

    channels = []
    visited = set()
    is_active = True
    current = origin

    while current is not None and current.pk not in visited:
        visited.add(current.pk)

        channel = WdmChannel.objects.filter(wdm_node=current, grid_position=grid_position).first()
        if channel is None:
            break
        channels.append(channel)

        tx_rp = _get_tx_rear_port(current)
        if tx_rp is None:
            break

        fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=tx_rp.pk)
        if not fresh_rp.cable_id:
            break

        cable = Cable.objects.get(pk=fresh_rp.cable_id)
        if cable.status != "connected":
            is_active = False

        next_node, _ = _get_far_end_node(tx_rp)
        if next_node is None:
            break

        current = next_node

    is_complete = False
    if len(channels) >= 2:
        first = channels[0]
        last = channels[-1]
        first_has_client = first.mux_front_port_id is not None or first.demux_front_port_id is not None
        last_has_client = last.mux_front_port_id is not None or last.demux_front_port_id is not None
        is_complete = first_has_client and last_has_client

    return {
        "channels": channels,
        "is_complete": is_complete,
        "is_active": is_active and len(channels) >= 2,
    }


@transaction.atomic
def rebuild_wavelength_paths_for_node(node):
    """Rebuild all WdmWavelengthPath records involving channels on this node."""
    grid_positions = WdmChannel.objects.filter(wdm_node=node).values_list("grid_position", flat=True).distinct()

    for gp in grid_positions:
        channel = WdmChannel.objects.filter(wdm_node=node, grid_position=gp).first()
        if channel is None:
            continue

        result = trace_wavelength_path(channel)
        channels = result["channels"]

        if len(channels) < 2:
            channel_pks = [ch.pk for ch in channels]
            orphan_paths = WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct()
            for path in orphan_paths:
                path.path_channels.all().delete()
                path.delete()
            continue

        channel_pks = [ch.pk for ch in channels]
        existing_path = WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct().first()

        if existing_path:
            path = existing_path
            path.grid_position = channels[0].grid_position
            path.wavelength_nm = channels[0].wavelength_nm
            path.is_complete = result["is_complete"]
            path.is_active = result["is_active"]
            path.save()
            path.path_channels.all().delete()
        else:
            path = WdmWavelengthPath.objects.create(
                grid_position=channels[0].grid_position,
                wavelength_nm=channels[0].wavelength_nm,
                is_complete=result["is_complete"],
                is_active=result["is_active"],
            )

        for seq, ch in enumerate(channels):
            WdmWavelengthPathChannel.objects.create(path=path, channel=ch, sequence=seq)

    WdmWavelengthPath.objects.filter(path_channels__isnull=True).delete()
