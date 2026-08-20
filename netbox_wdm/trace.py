"""Wavelength path tracing algorithm.

Discovers end-to-end wavelength paths by following cable connections
between WDM nodes, traversing through intermediate devices (patch panels, EDFAs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
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


class TraceCache:
    """Per-pass read cache for cable-chain walks.

    A rebuild pass traces every distinct grid position on a node, and each
    trace re-walks the same physical trunk: the rear ports, cables, strand
    pairings, port mappings, line ports, and channels it reads are identical
    from one walk to the next. This cache memoizes those read-only lookups so
    the first walk pays the queries and later walks are served from memory.

    An instance must not outlive a single pass (one rebuild call, or one
    standalone trace): entries are snapshots of the cabling state at first
    read, and reuse across transactions would serve stale data.
    """

    _MISS = object()  # sentinel; None is a valid cached value

    def __init__(self) -> None:
        self._store: dict[tuple, Any] = {}

    def _memo(self, key: tuple, compute) -> Any:
        value = self._store.get(key, self._MISS)
        if value is self._MISS:
            value = compute()
            self._store[key] = value
        return value

    def rear_port(self, pk: int) -> RearPort:
        """A fresh RearPort carrying its denormalized cable fields."""
        return self._memo(("rear_port", pk), lambda: RearPort.objects.get(pk=pk))

    def cable(self, pk: int) -> Cable:
        return self._memo(("cable", pk), lambda: Cable.objects.get(pk=pk))

    def far_end(self, termination: FrontPort | RearPort) -> FrontPort | RearPort | None:
        key = ("far_end", type(termination).__name__, termination.pk)
        return self._memo(key, lambda: _compute_cable_far_end(termination))

    def portmapping_for_front_port(self, front_port: FrontPort) -> PortMapping | None:
        return self._memo(
            ("pm_front", front_port.pk),
            lambda: PortMapping.objects.filter(front_port=front_port).select_related("rear_port").first(),
        )

    def portmapping_for_rear_port(self, rear_port: RearPort) -> PortMapping | None:
        return self._memo(
            ("pm_rear", rear_port.pk),
            lambda: PortMapping.objects.filter(rear_port=rear_port).select_related("front_port").first(),
        )

    def line_port(self, rear_port: RearPort) -> WdmLinePort | None:
        """The WdmLinePort on a rear port, or None (rear_port is unique per line port)."""
        return self._memo(
            ("line_port", rear_port.pk),
            lambda: WdmLinePort.objects.select_related("wdm_node", "module").filter(rear_port=rear_port).first(),
        )

    def line_rear_ports(self, node: WdmNode, module: Any, roles: tuple[str, ...]) -> list[RearPort]:
        key = ("line_rps", node.pk, module.pk if module else None, roles)
        return self._memo(
            key,
            lambda: [
                lp.rear_port
                for lp in WdmLinePort.objects.filter(wdm_node=node, module=module, role__in=roles).select_related(
                    "rear_port"
                )
            ],
        )

    def channel(self, node: WdmNode, module_id: int | None, grid_position: int) -> WdmChannel | None:
        """The channel at (node, module, grid position), or None (the triple is unique)."""
        key = ("channel", node.pk, module_id, grid_position)
        return self._memo(
            key,
            lambda: WdmChannel.objects.filter(wdm_node=node, module_id=module_id, grid_position=grid_position).first(),
        )


def _index_paired_far_end(termination: FrontPort | RearPort) -> FrontPort | RearPort | None:
    """Legacy strand pairing for unprofiled cables: Nth A-side pairs with Nth B-side.

    CableTermination rows carry no strand identity when the cable has no
    profile, so the Nth termination on one end (in pk order) is presumed to
    pair with the Nth termination on the other end. This only holds while
    termination rows keep their creation order; callers must treat the
    result as a guess.
    """
    all_terms = list(CableTermination.objects.filter(cable_id=termination.cable_id).order_by("cable_end", "pk"))
    my_ct = ContentType.objects.get_for_model(termination)

    my_terms = [t for t in all_terms if t.cable_end == termination.cable_end]
    my_index = next(
        (i for i, t in enumerate(my_terms) if t.termination_type_id == my_ct.pk and t.termination_id == termination.pk),
        None,
    )
    if my_index is None:
        return None

    far_terms = [t for t in all_terms if t.cable_end != termination.cable_end]
    if my_index >= len(far_terms):
        return None

    far = far_terms[my_index].termination
    return far if isinstance(far, (FrontPort, RearPort)) else None


def resolve_cable_far_end(
    termination: FrontPort | RearPort, cache: TraceCache | None = None
) -> FrontPort | RearPort | None:
    """Return the far-end port paired with this one on its cable strand.

    Profiled cables (NetBox 4.6+ ``Cable.profile``) persist the strand
    pairing on each ``CableTermination`` (connector/positions), and
    ``link_peers`` resolves the far end through the profile's connector
    mapping; that answer is authoritative.

    Unprofiled legacy cables fall back to index pairing (see
    ``_index_paired_far_end``), which may follow the wrong strand on
    multi-strand cables; a warning is logged whenever the pairing is
    resolved this way.

    The termination must be a fresh instance carrying its denormalized
    cable fields (cable, cable_end, cable_connector, cable_positions).
    When a ``cache`` is given, the resolution is memoized on it for the
    duration of the pass.
    """
    if cache is not None:
        return cache.far_end(termination)
    return _compute_cable_far_end(termination)


def _compute_cable_far_end(termination: FrontPort | RearPort) -> FrontPort | RearPort | None:
    """Uncached strand-pairing resolution behind resolve_cable_far_end."""
    if not termination.cable_id:  # type: ignore[attr-defined]
        return None

    cable = termination.cable
    if cable.profile:
        peers = [peer for peer in termination.link_peers if isinstance(peer, (FrontPort, RearPort))]
        return peers[0] if peers else None

    logger.warning(
        "Cable %s (pk %d) has no profile; guessing strand pairing by termination order. "
        "Assign a cable profile (e.g. trunk-2c1p for duplex trunks) to make strand pairing explicit.",
        cable,
        cable.pk,
    )
    return _index_paired_far_end(termination)


def _resolve_rearport_cable(
    current_rp: RearPort, visited: set[int], cache: TraceCache | None = None
) -> RearPort | None:
    """Follow a cable from a RearPort to the next RearPort.

    Handles both direct trunk cables (RP→RP) and patch cables through
    pass-through devices (RP→FP→PortMapping→RP→cable→RP→PortMapping→FP→RP).

    Returns the next RearPort or None. Updates visited set.
    """
    cache = cache if cache is not None else TraceCache()
    fresh_rp = cache.rear_port(current_rp.pk)
    far = resolve_cable_far_end(fresh_rp, cache)

    # Direct RearPort-to-RearPort trunk cable
    if isinstance(far, RearPort):
        return far

    # RearPort-to-FrontPort (patch cable into a pass-through device)
    if not isinstance(far, FrontPort):
        return None

    # FrontPort → PortMapping → RearPort (enter the pass-through device)
    pm_in = cache.portmapping_for_front_port(far)
    if pm_in is None or pm_in.rear_port.pk in visited:
        return None

    inner_rp = pm_in.rear_port
    visited.add(inner_rp.pk)

    # Follow cable from inner RearPort (e.g., trunk cable between patch panels)
    next_rp = resolve_cable_far_end(inner_rp, cache)
    if not isinstance(next_rp, RearPort):
        return None
    if next_rp.pk in visited:
        return None
    visited.add(next_rp.pk)

    # Check if next_rp is a WDM node directly — if so return it
    if cache.line_port(next_rp) is not None:
        return next_rp

    # Otherwise pass through another device: PortMapping → FrontPort → cable
    pm_exit = cache.portmapping_for_rear_port(next_rp)
    if pm_exit is None:
        return None

    exit_far = resolve_cable_far_end(pm_exit.front_port, cache)
    if isinstance(exit_far, FrontPort):
        # FP→FP link, then PortMapping→RP
        exit_pm = cache.portmapping_for_front_port(exit_far)
        if exit_pm is not None and exit_pm.rear_port.pk not in visited:
            return exit_pm.rear_port
        return None
    if isinstance(exit_far, RearPort):
        # FP→RP patch cable directly to the next device
        return exit_far
    return None


def _get_far_end_node(
    rear_port: RearPort, cache: TraceCache | None = None
) -> tuple[WdmNode | None, Any, RearPort | None]:
    """Follow cables from rear_port through intermediate devices until reaching a WDM node.

    Supports:
    1. Direct trunk cables: RearPort →(cable)→ RearPort
    2. Patch cables through pass-through devices (patch panels):
       RearPort →(cable)→ FrontPort →(PortMapping)→ RearPort →(cable)→
       RearPort →(PortMapping)→ FrontPort →(cable)→ RearPort

    Returns (WdmNode, Module | None, far_end_RearPort) or (None, None, None).
    """
    cache = cache if cache is not None else TraceCache()
    visited = {rear_port.pk}
    current_rp = rear_port
    max_hops = get_max_trace_hops()

    for _ in range(max_hops):  # bounded to prevent infinite loops
        far_rp = _resolve_rearport_cable(current_rp, visited, cache)
        if far_rp is None:
            return None, None, None

        if far_rp.pk in visited:
            return None, None, None
        visited.add(far_rp.pk)

        # Check if this rear port belongs to a WDM node
        lp = cache.line_port(far_rp)
        if lp is not None:
            return lp.wdm_node, lp.module, far_rp

        # Not a WDM node — continue from this rear port
        current_rp = far_rp

    warn_max_trace_hops_reached(rear_port, max_hops)
    return None, None, None


def _get_tx_rear_ports(node: WdmNode, module: Any, cache: TraceCache | None = None) -> list[RearPort]:
    """Get TX/BIDI rear ports for one module group of the node (module=None is the device group)."""
    from .choices import WdmLineRoleChoices

    cache = cache if cache is not None else TraceCache()
    return cache.line_rear_ports(node, module, (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI))


def _get_rx_rear_ports(node: WdmNode, module: Any, cache: TraceCache | None = None) -> list[RearPort]:
    """Get RX/BIDI rear ports for one module group of the node (module=None is the device group)."""
    from .choices import WdmLineRoleChoices

    cache = cache if cache is not None else TraceCache()
    return cache.line_rear_ports(node, module, (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI))


def _find_origin(
    node: WdmNode, module: Any, grid_position: int, cache: TraceCache | None = None
) -> tuple[WdmNode, Any]:
    """Walk backwards via RX ports to find the origin (node, module) for a grid position.

    Only considers a (node, module) as a predecessor if its TX port connects to
    the current (node, module)'s RX port (i.e., a forward-direction link).
    Tries all RX ports on multi-degree nodes (ROADM) to find the
    predecessor that leads furthest back.
    """
    cache = cache if cache is not None else TraceCache()
    visited = {(node.pk, module.pk if module else None)}
    current, current_module = node, module

    while True:
        rx_rps = _get_rx_rear_ports(current, current_module, cache)
        if not rx_rps:
            return current, current_module

        found = False
        for rx_rp in rx_rps:
            prev_node, prev_module, far_rp = _get_far_end_node(rx_rp, cache)
            if prev_node is None:
                continue
            key = (prev_node.pk, prev_module.pk if prev_module else None)
            if key in visited:
                continue

            # Verify the far-end rear port is actually a TX port (forward direction)
            tx_rps = _get_tx_rear_ports(prev_node, prev_module, cache)
            if not any(far_rp.pk == trp.pk for trp in tx_rps):  # pyright: ignore[reportOptionalMemberAccess]
                continue

            if cache.channel(prev_node, prev_module.pk if prev_module else None, grid_position) is None:
                continue

            visited.add(key)
            current, current_module = prev_node, prev_module
            found = True
            break

        if not found:
            return current, current_module


def _check_far_end_role(far_rp: RearPort, cache: TraceCache | None = None) -> bool:
    """Check if the far-end rear port has the correct role for receiving (RX or BIDI).

    Returns True if valid (RX/BIDI), False if invalid (TX — indicates TX-to-TX cabling).
    Returns True if no WdmLinePort exists (non-WDM device, passthrough).
    """
    from .choices import WdmLineRoleChoices

    cache = cache if cache is not None else TraceCache()
    lp = cache.line_port(far_rp)
    if lp is None:
        return True  # Not a WDM line port — no role to check

    return lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI)


def trace_wavelength_path(start_channel: WdmChannel, cache: TraceCache | None = None) -> TraceResult:
    """Trace a wavelength path starting from a channel.

    ``cache`` is a per-pass TraceCache shared across the traces of one
    rebuild pass; omit it for a standalone trace and a fresh one is used.
    """
    cache = cache if cache is not None else TraceCache()
    grid_position = start_channel.grid_position
    origin, origin_module = _find_origin(start_channel.wdm_node, start_channel.module, grid_position, cache)

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

        channel = cache.channel(current, current_module.pk if current_module else None, grid_position)
        if channel is None:
            break
        channels.append(channel)

        # Try all TX ports — prefer one that reaches an unvisited node
        # (critical for ROADM pass-through where multiple TX directions exist)
        tx_rps = _get_tx_rear_ports(current, current_module, cache)
        if not tx_rps:
            break

        next_node = None
        next_module = None
        far_rp = None
        for tx_rp in tx_rps:
            fresh_rp = cache.rear_port(tx_rp.pk)
            if not fresh_rp.cable_id:  # type: ignore[attr-defined]
                continue
            cable = cache.cable(fresh_rp.cable_id)  # type: ignore[attr-defined]
            if cable.status != "connected":
                is_active = False
            candidate, candidate_module, candidate_rp = _get_far_end_node(tx_rp, cache)
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

        if far_rp and not _check_far_end_role(far_rp, cache):
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
    """Rebuild all WdmWavelengthPath records involving channels on this node.

    All traces in the pass share one TraceCache: every grid position walks the
    same trunk, so the first trace pays the cable-chain queries and the rest
    are served from memory. The cache lives only for this call.
    """
    combos = list(WdmChannel.objects.filter(wdm_node=node).values_list("module_id", "grid_position").distinct())
    cache = TraceCache()

    for module_id, gp in combos:
        channel = cache.channel(node, module_id, gp)
        if channel is None:
            continue

        result = trace_wavelength_path(channel, cache)
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
