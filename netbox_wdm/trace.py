"""Wavelength path tracing algorithm.

Discovers end-to-end wavelength paths by following cable connections
between WDM nodes at matching grid positions.
"""

from dcim.models import CableTermination, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import WdmChannel, WdmLinePort, WdmWavelengthPath, WdmWavelengthPathChannel


def _get_far_end_node(rear_port):
    """Follow a cable from rear_port and return (WdmNode, far_end_RearPort) or (None, None)."""
    # Always fetch fresh cable_id from DB to handle stale in-memory objects
    fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=rear_port.pk)
    if not fresh_rp.cable_id:
        return None, None

    rp_ct = ContentType.objects.get_for_model(RearPort)
    far_terms = CableTermination.objects.filter(
        cable_id=fresh_rp.cable_id,
        termination_type=rp_ct,
    ).exclude(termination_id=fresh_rp.pk)

    far_term = far_terms.first()
    if far_term is None:
        return None, None

    try:
        far_rp = RearPort.objects.get(pk=far_term.termination_id)
    except RearPort.DoesNotExist:
        return None, None

    try:
        line_port = WdmLinePort.objects.select_related("wdm_node").get(rear_port=far_rp)
    except WdmLinePort.DoesNotExist:
        return None, None

    return line_port.wdm_node, far_rp


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

    The origin is the first node in the chain that has no predecessor at
    the given grid position. Tracks visited nodes to prevent infinite loops.
    """
    visited = {node.pk}
    current = node

    while True:
        rx_rp = _get_rx_rear_port(current)
        if rx_rp is None:
            return current

        prev_node, _ = _get_far_end_node(rx_rp)
        if prev_node is None:
            return current

        if prev_node.pk in visited:
            return current  # loop detected

        # Check if predecessor has a channel at this grid position
        if not WdmChannel.objects.filter(wdm_node=prev_node, grid_position=grid_position).exists():
            return current

        visited.add(prev_node.pk)
        current = prev_node


def trace_wavelength_path(start_channel):
    """Trace a wavelength path starting from a channel.

    Finds the origin first, then traces forward collecting all channels
    at the same grid position.

    Returns dict with:
        channels: list of WdmChannel in path order
        is_complete: bool - True if >= 2 channels and both endpoints have client ports
        is_active: bool - True if all trunk cables in the path are connected
    """
    from dcim.models import Cable

    grid_position = start_channel.grid_position
    origin = _find_origin(start_channel.wdm_node, grid_position)

    # Now trace forward from origin
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

        # Try to follow TX port forward
        tx_rp = _get_tx_rear_port(current)
        if tx_rp is None:
            break

        if not tx_rp.cable_id:
            break

        # Check cable status
        cable = Cable.objects.get(pk=tx_rp.cable_id)
        if cable.status != "connected":
            is_active = False

        next_node, _ = _get_far_end_node(tx_rp)
        if next_node is None:
            break

        current = next_node

    # Determine completeness
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
    """Rebuild all WdmWavelengthPath records involving channels on this node.

    For each grid_position on this node:
    1. Find the origin via _find_origin
    2. Trace forward from origin
    3. Create/update/delete WdmWavelengthPath records accordingly
    """
    grid_positions = WdmChannel.objects.filter(wdm_node=node).values_list("grid_position", flat=True).distinct()

    for gp in grid_positions:
        channel = WdmChannel.objects.filter(wdm_node=node, grid_position=gp).first()
        if channel is None:
            continue

        result = trace_wavelength_path(channel)
        channels = result["channels"]

        if len(channels) < 2:
            # Delete any existing paths that contain these channels
            channel_pks = [ch.pk for ch in channels]
            orphan_paths = WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct()
            for path in orphan_paths:
                path.path_channels.all().delete()
                path.delete()
            continue

        # Find existing path by checking if any of these channels already belong to a path
        channel_pks = [ch.pk for ch in channels]
        existing_path = WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct().first()

        if existing_path:
            path = existing_path
            path.grid_position = channels[0].grid_position
            path.wavelength_nm = channels[0].wavelength_nm
            path.is_complete = result["is_complete"]
            path.is_active = result["is_active"]
            path.save()
            # Rebuild channel entries
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

    # Clean up orphaned paths that have no channel entries
    WdmWavelengthPath.objects.filter(path_channels__isnull=True).delete()
