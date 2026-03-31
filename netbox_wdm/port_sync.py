"""Port sync detection and repair for WDM nodes.

Computes expected vs actual PortMapping state and provides sync operations.

Two validation modes based on node type:

**Fixed nodes** (terminal MUX, OADM, amplifier):
  Full validation — the exact set of (front_port_id, rear_port_id, grid_position)
  tuples must match between expected and actual PortMappings. MUX front ports map
  to TX/BIDI line ports, DEMUX front ports map to RX/BIDI line ports.

**ROADM nodes:**
  Position-only validation — channel-to-direction assignment is dynamic, so we
  don't validate which rear port a front port maps to. We only check that every
  existing PortMapping for a channel front port has the correct rear_port_position
  matching the channel's grid_position.

EXP/1310 pass-through PortMappings are excluded from both hashes since they are
not part of any WdmChannel.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from dcim.models import PortMapping

from .choices import WdmLineRoleChoices

if TYPE_CHECKING:
    from .models import WdmNode


def _hash_tuples(tuples: list[tuple[int, ...]]) -> str:
    """Compute SHA-256 hex digest from a sorted list of int tuples."""
    if not tuples:
        return ""
    sorted_tuples = sorted(tuples)
    data = ",".join(":".join(str(v) for v in t) for t in sorted_tuples)
    return hashlib.sha256(data.encode()).hexdigest()


def _get_channel_fp_ids(node: WdmNode) -> set[int]:
    """Collect all front_port_ids from WdmChannels (mux and demux, excluding None)."""
    fp_ids: set[int] = set()
    for ch in node.channels.all():
        if ch.mux_front_port_id is not None:
            fp_ids.add(ch.mux_front_port_id)
        if ch.demux_front_port_id is not None:
            fp_ids.add(ch.demux_front_port_id)
    return fp_ids


# ---------------------------------------------------------------------------
# Fixed node hash: full (fp_id, rp_id, grid_position) comparison
# ---------------------------------------------------------------------------


def _compute_expected_hash_fixed(node: WdmNode) -> str:
    """Expected hash for fixed nodes: full cross-product of channels × matching line ports."""
    line_ports = list(node.line_ports.select_related("rear_port").order_by("direction", "role"))
    if not line_ports:
        return ""

    tx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI)]
    rx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI)]

    tuples: list[tuple[int, ...]] = []
    for ch in node.channels.order_by("grid_position"):
        if ch.mux_front_port_id is not None:
            for rp_id in tx_rp_ids:
                tuples.append((ch.mux_front_port_id, rp_id, ch.grid_position))
        if ch.demux_front_port_id is not None:
            for rp_id in rx_rp_ids:
                tuples.append((ch.demux_front_port_id, rp_id, ch.grid_position))

    return _hash_tuples(tuples)


def _compute_actual_hash_fixed(node: WdmNode) -> str:
    """Actual hash for fixed nodes: (fp_id, rp_id, rear_port_position) from PortMappings."""
    line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
    if not line_port_rp_ids:
        return ""

    channel_fp_ids = _get_channel_fp_ids(node)
    if not channel_fp_ids:
        return ""

    mappings = PortMapping.objects.filter(
        device=node.device,
        front_port_id__in=channel_fp_ids,
        rear_port_id__in=line_port_rp_ids,
    ).values_list("front_port_id", "rear_port_id", "rear_port_position")
    return _hash_tuples([(fp, rp, pos) for fp, rp, pos in mappings])


# ---------------------------------------------------------------------------
# ROADM hash: position-only (fp_id, grid_position) comparison
# ---------------------------------------------------------------------------


def _compute_expected_hash_roadm(node: WdmNode) -> str:
    """Expected hash for ROADMs: (fp_id, grid_position) for each mapped channel front port."""
    tuples: list[tuple[int, ...]] = []
    for ch in node.channels.order_by("grid_position"):
        if ch.mux_front_port_id is not None:
            tuples.append((ch.mux_front_port_id, ch.grid_position))
        if ch.demux_front_port_id is not None:
            tuples.append((ch.demux_front_port_id, ch.grid_position))
    return _hash_tuples(tuples)


def _compute_actual_hash_roadm(node: WdmNode) -> str:
    """Actual hash for ROADMs: (fp_id, rear_port_position) from existing PortMappings.

    Ignores which rear_port the mapping points to — only checks that the position
    is correct. Deduplicates since the same front port may map to multiple rear ports.
    """
    line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
    if not line_port_rp_ids:
        return ""

    channel_fp_ids = _get_channel_fp_ids(node)
    if not channel_fp_ids:
        return ""

    mappings = PortMapping.objects.filter(
        device=node.device,
        front_port_id__in=channel_fp_ids,
        rear_port_id__in=line_port_rp_ids,
    ).values_list("front_port_id", "rear_port_position")
    # Deduplicate: same fp may map to multiple rear ports at the same position
    unique_tuples = {(fp, pos) for fp, pos in mappings}
    return _hash_tuples(list(unique_tuples))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_expected_port_hash(node: WdmNode) -> str:
    """Compute the expected port hash, dispatching by node type."""
    if node.is_fixed:
        return _compute_expected_hash_fixed(node)
    return _compute_expected_hash_roadm(node)


def compute_actual_port_hash(node: WdmNode) -> str:
    """Compute the actual port hash, dispatching by node type."""
    if node.is_fixed:
        return _compute_actual_hash_fixed(node)
    return _compute_actual_hash_roadm(node)


def check_port_sync(node: WdmNode) -> bool:
    """Check if the node's port mappings are in sync. Returns True if in sync."""
    expected = compute_expected_port_hash(node)
    actual = compute_actual_port_hash(node)
    return expected == actual


# ---------------------------------------------------------------------------
# Diff and sync
# ---------------------------------------------------------------------------


def _build_expected_mappings_fixed(node: WdmNode) -> set[tuple[int, int, int]]:
    """Build expected (front_port_id, rear_port_id, grid_position) tuples for fixed nodes."""
    line_ports = list(node.line_ports.select_related("rear_port").all())
    tx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI)]
    rx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI)]

    expected: set[tuple[int, int, int]] = set()
    for ch in node.channels.all():
        if ch.mux_front_port_id is not None:
            for rp_id in tx_rp_ids:
                expected.add((ch.mux_front_port_id, rp_id, ch.grid_position))
        if ch.demux_front_port_id is not None:
            for rp_id in rx_rp_ids:
                expected.add((ch.demux_front_port_id, rp_id, ch.grid_position))
    return expected


def _build_actual_mappings(node: WdmNode) -> set[tuple[int, int, int]]:
    """Build the set of actual (front_port_id, rear_port_id, rear_port_position) tuples.

    Only considers PortMappings for WdmChannel front ports and WdmLinePort rear ports.
    """
    line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
    channel_fp_ids = _get_channel_fp_ids(node)

    if not line_port_rp_ids or not channel_fp_ids:
        return set()

    mappings = PortMapping.objects.filter(
        device=node.device,
        front_port_id__in=channel_fp_ids,
        rear_port_id__in=line_port_rp_ids,
    ).values_list("front_port_id", "rear_port_id", "rear_port_position")
    return {(fp, rp, pos) for fp, rp, pos in mappings}


def _compute_roadm_position_errors(node: WdmNode) -> tuple[set[tuple[int, int, int]], set[tuple[int, int, int]]]:
    """For ROADMs: find PortMappings with wrong positions.

    Returns (to_delete, to_recreate) — mappings that have the wrong rear_port_position
    and the corrected versions to recreate.
    """
    actual = _build_actual_mappings(node)
    # Build fp_id → grid_position lookup from channels
    fp_to_grid: dict[int, int] = {}
    for ch in node.channels.all():
        if ch.mux_front_port_id is not None:
            fp_to_grid[ch.mux_front_port_id] = ch.grid_position
        if ch.demux_front_port_id is not None:
            fp_to_grid[ch.demux_front_port_id] = ch.grid_position

    to_delete: set[tuple[int, int, int]] = set()
    to_recreate: set[tuple[int, int, int]] = set()
    for fp_id, rp_id, pos in actual:
        expected_pos = fp_to_grid.get(fp_id)
        if expected_pos is not None and pos != expected_pos:
            to_delete.add((fp_id, rp_id, pos))
            to_recreate.add((fp_id, rp_id, expected_pos))

    return to_delete, to_recreate


def compute_sync_diff(node: WdmNode) -> dict[str, Any]:
    """Compute the full diff between expected and actual port state.

    Fixed nodes: full set comparison of expected vs actual mappings.
    ROADM nodes: only detect wrong-position mappings (direction assignment is dynamic).
    """
    from dcim.models import FrontPort, FrontPortTemplate, RearPortTemplate

    if node.is_fixed:
        expected = _build_expected_mappings_fixed(node)
        actual = _build_actual_mappings(node)
        to_create = expected - actual
        to_delete = actual - expected
    else:
        to_delete, to_create = _compute_roadm_position_errors(node)

    # Structural check: find expected ports from DeviceType template missing on device
    device_type = node.device.device_type
    front_ports_to_create: list[dict[str, Any]] = []
    rear_ports_to_create: list[dict[str, Any]] = []

    existing_rp_names = set(node.device.rearports.values_list("name", flat=True))
    for rpt in RearPortTemplate.objects.filter(device_type=device_type):
        if rpt.name not in existing_rp_names:
            rear_ports_to_create.append({"name": rpt.name, "type": rpt.type, "positions": rpt.positions})

    existing_fp_names = set(FrontPort.objects.filter(device=node.device).values_list("name", flat=True))
    for fpt in FrontPortTemplate.objects.filter(device_type=device_type):
        if fpt.name not in existing_fp_names:
            front_ports_to_create.append({"name": fpt.name, "type": fpt.type})

    # Warnings: count cables connected to line port rear ports
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
    cables_affected = 0
    if line_port_rp_ids:
        rp_ct = ContentType.objects.get_for_model(RearPort)
        cables_affected = (
            CableTermination.objects.filter(termination_type=rp_ct, termination_id__in=line_port_rp_ids)
            .values_list("cable_id", flat=True)
            .distinct()
            .count()
        )

    from .models import WdmCircuit, WdmWavelengthPathChannel

    channel_ids = list(node.channels.values_list("pk", flat=True))
    path_ids = (
        WdmWavelengthPathChannel.objects.filter(channel_id__in=channel_ids).values_list("path_id", flat=True).distinct()
    )
    affected_circuits = list(WdmCircuit.objects.filter(wavelength_path_id__in=path_ids).values("id", "name"))

    return {
        "warnings": {
            "cables_affected": cables_affected,
            "wavelength_services": [{"id": c["id"], "display": c["name"]} for c in affected_circuits],
        },
        "changes": {
            "rear_ports": {"create": rear_ports_to_create},
            "front_ports": {"create": front_ports_to_create},
            "port_mappings": {"delete": len(to_delete), "create": len(to_create)},
        },
    }


def apply_sync(node: WdmNode) -> dict[str, Any]:
    """Apply port sync: structural repair then PortMapping reset.

    Phase 1: Create missing FrontPorts/RearPorts from DeviceType template.
    Phase 2: Delete all WDM-related PortMappings, recreate from channel grid.
    """
    from dcim.models import FrontPort, FrontPortTemplate, RearPort, RearPortTemplate
    from django.db import transaction

    with transaction.atomic():
        device = node.device
        device_type = device.device_type

        # Phase 1: Create missing RearPorts
        existing_rp_names = set(device.rearports.values_list("name", flat=True))
        rear_ports_created: list[dict[str, Any]] = []
        for rpt in RearPortTemplate.objects.filter(device_type=device_type):
            if rpt.name not in existing_rp_names:
                RearPort.objects.create(device=device, name=rpt.name, type=rpt.type, positions=rpt.positions)
                rear_ports_created.append({"name": rpt.name, "type": rpt.type, "positions": rpt.positions})

        # Phase 1: Create missing FrontPorts
        existing_fp_names = set(FrontPort.objects.filter(device=device).values_list("name", flat=True))
        front_ports_created: list[dict[str, Any]] = []
        for fpt in FrontPortTemplate.objects.filter(device_type=device_type):
            if fpt.name not in existing_fp_names:
                from dcim.models.device_component_templates import PortTemplateMapping

                ptm = PortTemplateMapping.objects.filter(device_type=device_type, front_port=fpt).first()
                if ptm:
                    rp = RearPort.objects.filter(device=device, name=ptm.rear_port.name).first()
                    if rp:
                        FrontPort.objects.create(
                            device=device,
                            name=fpt.name,
                            type=fpt.type,
                            rear_port=rp,
                            rear_port_position=ptm.rear_port_position,
                        )
                        front_ports_created.append({"name": fpt.name, "type": fpt.type})

        # Phase 2: PortMapping repair
        if node.is_fixed:
            expected = _build_expected_mappings_fixed(node)
            actual = _build_actual_mappings(node)
            to_create = expected - actual
            to_delete = actual - expected
        else:
            to_delete, to_create = _compute_roadm_position_errors(node)

        deleted_count = 0
        if to_delete:
            from django.db.models import Q

            delete_q = Q()
            for fp_id, rp_id, grid_pos in to_delete:
                delete_q |= Q(device=device, front_port_id=fp_id, rear_port_id=rp_id, rear_port_position=grid_pos)
            deleted_count, _ = PortMapping.objects.filter(delete_q).delete()

        new_mappings = [
            PortMapping(
                device=device,
                front_port_id=fp_id,
                rear_port_id=rp_id,
                front_port_position=1,
                rear_port_position=grid_pos,
            )
            for fp_id, rp_id, grid_pos in to_create
        ]
        if new_mappings:
            PortMapping.objects.bulk_create(new_mappings)

        # Retrace affected CablePaths
        from .api.views import _retrace_affected_paths

        line_ports = list(node.line_ports.select_related("rear_port").all())
        _retrace_affected_paths(node, line_ports)

        # Update hash and flag
        node.expected_port_hash = compute_expected_port_hash(node)
        node.port_sync_valid = True
        node.save(update_fields=["expected_port_hash", "port_sync_valid"])

    # Compute warnings for the report (outside transaction, after sync)
    diff_for_warnings = compute_sync_diff(node)

    return {
        "warnings": diff_for_warnings["warnings"],
        "changes": {
            "rear_ports": {"create": rear_ports_created},
            "front_ports": {"create": front_ports_created},
            "port_mappings": {"delete": deleted_count, "create": len(new_mappings)},
        },
    }
