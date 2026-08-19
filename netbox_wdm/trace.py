"""Wavelength path tracing algorithm.

Discovers end-to-end wavelength paths by following cable connections
between WDM nodes, traversing through intermediate devices (patch panels, EDFAs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from netbox.plugins import get_plugin_config

from .models import WdmChannel, WdmLinePort, WdmNode, WdmWavelengthPath, WdmWavelengthPathChannel

logger = logging.getLogger(__name__)


def get_max_trace_hops() -> int:
    """Return the configured hop cap for cable-chain walks (max_trace_hops plugin setting)."""
    return get_plugin_config("netbox_wdm", "max_trace_hops", 20)


def warn_max_trace_hops_reached(start_rp: RearPort, max_hops: int) -> None:
    """Log that a cable-chain walk was truncated by the hop cap, so the incomplete path is visible."""
    logger.warning(
        "Cable trace from rear port %s on device %s stopped after %d hops; the traced path may be "
        "incomplete. Raise the max_trace_hops plugin setting if the chain is legitimately longer.",
        start_rp,
        start_rp.device,
        max_hops,
    )


@dataclass
class TraceResult:
    """Result of tracing a wavelength path."""

    channels: list[WdmChannel]
    is_complete: bool
    is_active: bool
    is_valid: bool


def _follow_cable_from_rearport(rear_port: RearPort) -> RearPort | None:
    """Follow a cable from a rear port to its paired far-end rear port.

    Handles multi-termination trunk cables by matching position in the ordered
    termination list (first A-side maps to first B-side, etc).

    Returns the far-end RearPort or None.
    """
    fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=rear_port.pk)
    if not fresh_rp.cable_id:  # type: ignore[attr-defined]
        return None

    rp_ct = ContentType.objects.get_for_model(RearPort)

    # Get all terminations for this cable, ordered by PK (creation order = position)
    all_terms = list(
        CableTermination.objects.filter(
            cable_id=fresh_rp.cable_id,
            termination_type=rp_ct,  # type: ignore[attr-defined]
        ).order_by("cable_end", "pk")
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


def _follow_frontport_cable(front_port: FrontPort) -> FrontPort | None:
    """Follow a cable from a front port to its paired far-end front port.

    Handles multi-termination cables by matching position.
    Returns the far-end FrontPort or None.
    """
    if not front_port.cable_id:  # type: ignore[attr-defined]
        return None

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    all_terms = list(
        CableTermination.objects.filter(
            cable_id=front_port.cable_id,
            termination_type=fp_ct,  # type: ignore[attr-defined]
        ).order_by("cable_end", "pk")
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


def _follow_cable_from_rearport_to_frontport(rear_port: RearPort) -> FrontPort | None:
    """Follow a cable from a rear port to a far-end front port (patch cable pattern).

    Returns the far-end FrontPort or None.
    """
    fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=rear_port.pk)
    if not fresh_rp.cable_id:  # type: ignore[attr-defined]
        return None

    rp_ct = ContentType.objects.get_for_model(RearPort)
    fp_ct = ContentType.objects.get_for_model(FrontPort)

    # Find which side the rear port is on
    rp_terms = list(
        CableTermination.objects.filter(
            cable_id=fresh_rp.cable_id,  # pyright: ignore[reportAttributeAccessIssue]
            termination_type=rp_ct,  # type: ignore[attr-defined]
        ).order_by("cable_end", "pk")
    )
    fp_terms = list(
        CableTermination.objects.filter(
            cable_id=fresh_rp.cable_id,  # pyright: ignore[reportAttributeAccessIssue]
            termination_type=fp_ct,  # type: ignore[attr-defined]
        ).order_by("cable_end", "pk")
    )

    if not fp_terms:
        return None

    my_side = None
    my_index = -1
    a_rp_terms = [t for t in rp_terms if t.cable_end == "A"]
    b_rp_terms = [t for t in rp_terms if t.cable_end == "B"]

    for i, t in enumerate(a_rp_terms):
        if t.termination_id == fresh_rp.pk:
            my_side = "A"
            my_index = i
            break
    if my_side is None:
        for i, t in enumerate(b_rp_terms):
            if t.termination_id == fresh_rp.pk:
                my_side = "B"
                my_index = i
                break

    if my_side is None or my_index < 0:
        return None

    far_fp_terms = [t for t in fp_terms if t.cable_end != my_side]
    if my_index >= len(far_fp_terms):
        return None

    try:
        return FrontPort.objects.select_related("device").get(pk=far_fp_terms[my_index].termination_id)
    except FrontPort.DoesNotExist:
        return None


def _resolve_rearport_cable(current_rp: RearPort, visited: set[int]) -> RearPort | None:
    """Follow a cable from a RearPort to the next RearPort.

    Handles both direct trunk cables (RP→RP) and patch cables through
    pass-through devices (RP→FP→PortMapping→RP→cable→RP→PortMapping→FP→RP).

    Returns the next RearPort or None. Updates visited set.
    """
    # Try direct RearPort-to-RearPort cable first
    far_rp = _follow_cable_from_rearport(current_rp)
    if far_rp is not None:
        return far_rp

    # Try RearPort-to-FrontPort (patch cable into a pass-through device)
    far_fp = _follow_cable_from_rearport_to_frontport(current_rp)
    if far_fp is None:
        return None

    # FrontPort → PortMapping → RearPort (enter the pass-through device)
    pm_in = PortMapping.objects.filter(front_port=far_fp).select_related("rear_port").first()
    if pm_in is None or pm_in.rear_port.pk in visited:
        return None

    inner_rp = pm_in.rear_port
    visited.add(inner_rp.pk)

    # Follow cable from inner RearPort (e.g., trunk cable between patch panels)
    next_rp = _follow_cable_from_rearport(inner_rp)
    if next_rp is not None:
        if next_rp.pk in visited:
            return None
        visited.add(next_rp.pk)

        # Check if next_rp is a WDM node directly — if so return it
        try:
            WdmLinePort.objects.get(rear_port=next_rp)
            return next_rp
        except WdmLinePort.DoesNotExist:
            pass

        # Otherwise pass through another device: PortMapping → FrontPort → cable → RearPort
        pm_exit = PortMapping.objects.filter(rear_port=next_rp).select_related("front_port").first()
        if pm_exit is None:
            return None

        exit_fp = pm_exit.front_port
        if not exit_fp.cable_id:  # type: ignore[attr-defined]
            return None

        # Follow FrontPort cable — could go to RearPort (patch cable out)
        exit_far_fp = _follow_frontport_cable(exit_fp)
        if exit_far_fp is not None:
            # FP→FP link, then PortMapping→RP
            exit_pm = PortMapping.objects.filter(front_port=exit_far_fp).select_related("rear_port").first()
            if exit_pm is not None and exit_pm.rear_port.pk not in visited:
                return exit_pm.rear_port

        # Try FrontPort→RearPort cable (patch cable to WDM device)
        # Check CableTermination for RearPort on far end of exit_fp's cable
        rp_ct = ContentType.objects.get_for_model(RearPort)
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        all_terms = list(
            CableTermination.objects.filter(
                cable_id=exit_fp.cable_id  # type: ignore[attr-defined]
            ).order_by("cable_end", "pk")
        )
        my_side = None
        for t in all_terms:
            if t.termination_type == fp_ct and t.termination_id == exit_fp.pk:
                my_side = t.cable_end
                break
        if my_side:
            # Position-match: find exit_fp's index among FP terms on my side
            my_fp_terms = [t for t in all_terms if t.cable_end == my_side and t.termination_type == fp_ct]
            my_fp_idx = next((i for i, t in enumerate(my_fp_terms) if t.termination_id == exit_fp.pk), 0)

            far_rp_terms = [t for t in all_terms if t.cable_end != my_side and t.termination_type == rp_ct]
            if my_fp_idx < len(far_rp_terms):
                try:
                    return RearPort.objects.get(pk=far_rp_terms[my_fp_idx].termination_id)
                except RearPort.DoesNotExist:
                    pass

    return None


def _get_far_end_node(rear_port: RearPort) -> tuple[WdmNode | None, Any, RearPort | None]:
    """Follow cables from rear_port through intermediate devices until reaching a WDM node.

    Supports:
    1. Direct trunk cables: RearPort →(cable)→ RearPort
    2. Patch cables through pass-through devices (patch panels):
       RearPort →(cable)→ FrontPort →(PortMapping)→ RearPort →(cable)→
       RearPort →(PortMapping)→ FrontPort →(cable)→ RearPort

    Returns (WdmNode, Module | None, far_end_RearPort) or (None, None, None).
    """
    visited = {rear_port.pk}
    current_rp = rear_port
    max_hops = get_max_trace_hops()

    for _ in range(max_hops):  # bounded to prevent infinite loops
        far_rp = _resolve_rearport_cable(current_rp, visited)
        if far_rp is None:
            return None, None, None

        if far_rp.pk in visited:
            return None, None, None
        visited.add(far_rp.pk)

        # Check if this rear port belongs to a WDM node
        lp = WdmLinePort.objects.select_related("wdm_node", "module").filter(rear_port=far_rp).first()
        if lp is not None:
            return lp.wdm_node, lp.module, far_rp

        # Not a WDM node — continue from this rear port
        current_rp = far_rp

    warn_max_trace_hops_reached(rear_port, max_hops)
    return None, None, None


def _get_tx_rear_ports(node: WdmNode, module: Any) -> list[RearPort]:
    """Get TX/BIDI rear ports for one module group of the node (module=None is the device group)."""
    from .choices import WdmLineRoleChoices

    return [
        lp.rear_port
        for lp in WdmLinePort.objects.filter(
            wdm_node=node, module=module, role__in=[WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI]
        ).select_related("rear_port")
    ]


def _get_rx_rear_ports(node: WdmNode, module: Any) -> list[RearPort]:
    """Get RX/BIDI rear ports for one module group of the node (module=None is the device group)."""
    from .choices import WdmLineRoleChoices

    return [
        lp.rear_port
        for lp in WdmLinePort.objects.filter(
            wdm_node=node, module=module, role__in=[WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI]
        ).select_related("rear_port")
    ]


def _find_origin(node: WdmNode, module: Any, grid_position: int) -> tuple[WdmNode, Any]:
    """Walk backwards via RX ports to find the origin (node, module) for a grid position.

    Only considers a (node, module) as a predecessor if its TX port connects to
    the current (node, module)'s RX port (i.e., a forward-direction link).
    Tries all RX ports on multi-degree nodes (ROADM) to find the
    predecessor that leads furthest back.
    """
    visited = {(node.pk, module.pk if module else None)}
    current, current_module = node, module

    while True:
        rx_rps = _get_rx_rear_ports(current, current_module)
        if not rx_rps:
            return current, current_module

        found = False
        for rx_rp in rx_rps:
            prev_node, prev_module, far_rp = _get_far_end_node(rx_rp)
            if prev_node is None:
                continue
            key = (prev_node.pk, prev_module.pk if prev_module else None)
            if key in visited:
                continue

            # Verify the far-end rear port is actually a TX port (forward direction)
            tx_rps = _get_tx_rear_ports(prev_node, prev_module)
            if not any(far_rp.pk == trp.pk for trp in tx_rps):  # pyright: ignore[reportOptionalMemberAccess]
                continue

            if not WdmChannel.objects.filter(
                wdm_node=prev_node, module=prev_module, grid_position=grid_position
            ).exists():
                continue

            visited.add(key)
            current, current_module = prev_node, prev_module
            found = True
            break

        if not found:
            return current, current_module


def _check_far_end_role(far_rp: RearPort) -> bool:
    """Check if the far-end rear port has the correct role for receiving (RX or BIDI).

    Returns True if valid (RX/BIDI), False if invalid (TX — indicates TX-to-TX cabling).
    Returns True if no WdmLinePort exists (non-WDM device, passthrough).
    """
    from .choices import WdmLineRoleChoices

    try:
        lp = WdmLinePort.objects.get(rear_port=far_rp)
    except WdmLinePort.DoesNotExist:
        return True  # Not a WDM line port — no role to check

    return lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI)


def trace_wavelength_path(start_channel: WdmChannel) -> TraceResult:
    """Trace a wavelength path starting from a channel."""
    from dcim.models import Cable

    grid_position = start_channel.grid_position
    origin, origin_module = _find_origin(start_channel.wdm_node, start_channel.module, grid_position)

    channels = []
    visited = set()
    is_active = True
    is_valid = True
    current, current_module = origin, origin_module

    while current is not None:
        key = (current.pk, current_module.pk if current_module else None)
        if key in visited:
            break
        visited.add(key)

        channel = WdmChannel.objects.filter(
            wdm_node=current, module=current_module, grid_position=grid_position
        ).first()
        if channel is None:
            break
        channels.append(channel)

        # Try all TX ports — prefer one that reaches an unvisited node
        # (critical for ROADM pass-through where multiple TX directions exist)
        tx_rps = _get_tx_rear_ports(current, current_module)
        if not tx_rps:
            break

        next_node = None
        next_module = None
        far_rp = None
        for tx_rp in tx_rps:
            fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=tx_rp.pk)
            if not fresh_rp.cable_id:  # type: ignore[attr-defined]
                continue
            cable = Cable.objects.get(pk=fresh_rp.cable_id)  # type: ignore[attr-defined]
            if cable.status != "connected":
                is_active = False
            candidate, candidate_module, candidate_rp = _get_far_end_node(tx_rp)
            if candidate is None:
                continue
            candidate_key = (candidate.pk, candidate_module.pk if candidate_module else None)
            if candidate_key not in visited:
                next_node = candidate
                next_module = candidate_module
                far_rp = candidate_rp
                break

        if next_node is None:
            break

        if far_rp and not _check_far_end_role(far_rp):
            is_valid = False

        current, current_module = next_node, next_module

    is_complete = False
    if len(channels) >= 2:
        first = channels[0]
        last = channels[-1]
        first_has_client = first.mux_front_port_id is not None or first.demux_front_port_id is not None
        last_has_client = last.mux_front_port_id is not None or last.demux_front_port_id is not None
        is_complete = first_has_client and last_has_client

    return TraceResult(
        channels=channels,
        is_complete=is_complete,
        is_active=is_active and len(channels) >= 2,
        is_valid=is_valid,
    )


@transaction.atomic
def rebuild_wavelength_paths_for_node(node: WdmNode) -> None:
    """Rebuild all WdmWavelengthPath records involving channels on this node."""
    combos = list(WdmChannel.objects.filter(wdm_node=node).values_list("module_id", "grid_position").distinct())

    for module_id, gp in combos:
        channel = WdmChannel.objects.filter(wdm_node=node, module_id=module_id, grid_position=gp).first()
        if channel is None:
            continue

        result = trace_wavelength_path(channel)
        channels = result.channels

        if len(channels) < 2:
            channel_pks = [ch.pk for ch in channels]
            # Only delete paths whose exact sequence matches these channels
            for candidate in WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct():
                candidate_pks = list(candidate.path_channels.order_by("sequence").values_list("channel_id", flat=True))
                if set(candidate_pks) <= set(channel_pks):
                    candidate.path_channels.all().delete()
                    candidate.delete()
            continue

        channel_pks = [ch.pk for ch in channels]

        # Find an existing path with the same channels in the same sequence order.
        # This preserves both directions for duplex (e.g., [A,B] and [B,A] are distinct).
        existing_path = None
        for candidate in WdmWavelengthPath.objects.filter(path_channels__channel__pk__in=channel_pks).distinct():
            candidate_pks = list(candidate.path_channels.order_by("sequence").values_list("channel_id", flat=True))
            if candidate_pks == channel_pks:
                existing_path = candidate
                break

        if existing_path:
            path = existing_path
            path.grid_position = channels[0].grid_position
            path.wavelength_nm = channels[0].wavelength_nm
            path.is_complete = result.is_complete
            path.is_active = result.is_active
            path.is_valid = result.is_valid
            path.save()
            path.path_channels.all().delete()
        else:
            path = WdmWavelengthPath.objects.create(
                grid_position=channels[0].grid_position,
                wavelength_nm=channels[0].wavelength_nm,
                is_complete=result.is_complete,
                is_active=result.is_active,
                is_valid=result.is_valid,
            )

        for seq, ch in enumerate(channels):
            WdmWavelengthPathChannel.objects.create(path=path, channel=ch, sequence=seq)

    WdmWavelengthPath.objects.filter(path_channels__isnull=True).delete()
