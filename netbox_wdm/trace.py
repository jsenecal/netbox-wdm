"""Wavelength path tracing algorithm.

Discovers end-to-end wavelength paths by following cable connections
between WDM nodes, traversing through intermediate devices (patch panels, EDFAs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dcim.models import Cable, RearPort
from django.db import transaction

from .core_walk import walk_from_rear_port
from .models import WdmChannel, WdmLinePort, WdmNode, WdmWavelengthPath, WdmWavelengthPathChannel

logger = logging.getLogger(__name__)


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

    def walk(self, rear_port: RearPort) -> list[list[Any]] | None:
        """The ordered cable-chain node groups leaving a rear port, or None."""
        return self._memo(("walk", rear_port.pk), lambda: walk_from_rear_port(rear_port))

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


def _pick_far_line_port(candidates: list[tuple[WdmLinePort, RearPort]], origin_role: str | None):
    """Choose which of several reachable line ports a signal actually lands on.

    A profiled cable resolves to one strand, so there is normally a single
    candidate. Unprofiled multi-terminated cables carry no strand identity,
    so core follows every fibre at once and both far line ports come back;
    the signal leaving a TX lands on the RX, and vice versa. Picking by role
    reads the direction off the WDM overlay rather than guessing it from
    termination row order.

    A genuine TX-to-TX miscable is unaffected: it resolves to one strand and
    so reaches here as a single candidate, still flagged by
    ``_check_far_end_role``.
    """
    from .choices import WdmLineRoleChoices

    if len(candidates) == 1 or origin_role is None:
        return candidates[0]

    complements = {
        WdmLineRoleChoices.TX: (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI),
        WdmLineRoleChoices.RX: (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI),
        WdmLineRoleChoices.BIDI: (WdmLineRoleChoices.BIDI, WdmLineRoleChoices.RX, WdmLineRoleChoices.TX),
    }.get(origin_role, ())

    for role in complements:
        for candidate in candidates:
            if candidate[0].role == role:
                return candidate
    return candidates[0]


def far_line_port_in_group(group: list[Any], line_port_lookup, origin_role: str | None):
    """Return the (WdmLinePort, RearPort) a chain reaches within one walk group, or None.

    Shared by the two consumers of a walk -- path discovery in this module
    and trace rendering in ``views`` -- so the rule for which rear port
    counts as the far end lives in one place. ``line_port_lookup`` maps a
    rear port to its WdmLinePort, letting a caller supply a cached lookup.
    """
    candidates = []
    for obj in group:
        if not isinstance(obj, RearPort):
            continue
        lp = line_port_lookup(obj)
        if lp is not None:
            candidates.append((lp, obj))
    if not candidates:
        return None
    return _pick_far_line_port(candidates, origin_role)


def _get_far_end_node(
    rear_port: RearPort, cache: TraceCache | None = None
) -> tuple[WdmNode | None, Any, RearPort | None]:
    """Follow the cable chain from rear_port to the next WDM node along it.

    The chain may pass through any number of intermediate devices in any
    cabling permutation, and may cross a carrier circuit mid-span; the walk
    itself is core's (see ``core_walk``). The first rear ports along it that
    carry a WdmLinePort are the far end, so a chain that reaches an
    amplifier or another WDM node stops there rather than running on.

    Returns (WdmNode, Module | None, far_end_RearPort) or (None, None, None).
    """
    cache = cache if cache is not None else TraceCache()
    groups = cache.walk(rear_port)
    if groups is None:
        return None, None, None

    origin_lp = cache.line_port(rear_port)
    origin_role = origin_lp.role if origin_lp is not None else None

    for group in groups[1:]:  # group 0 is the origin rear port itself
        found = far_line_port_in_group(group, cache.line_port, origin_role)
        if found is not None:
            lp, far_rp = found
            return lp.wdm_node, lp.module, far_rp

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
