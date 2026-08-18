"""Port sync detection and repair for WDM nodes.

Computes expected vs actual PortMapping state and provides sync operations.

Channels and line ports are split into per-module groups (`_node_groups`): the
device-level group (module is None) plus one group per installed module. Each
group is validated independently using one of two modes, resolved from the
module's profile when module-scoped, or the node's own type otherwise:

**Fixed groups** (terminal MUX, OADM, amplifier):
  Full validation — the exact set of (front_port_id, rear_port_id, grid_position)
  tuples must match between expected and actual PortMappings, scoped to that
  group's own line ports. MUX front ports map to TX/BIDI line ports, DEMUX front
  ports map to RX/BIDI line ports. A group never cross-products against another
  module's line ports.

**ROADM groups:**
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


def _hash_tuples(tuples: list[tuple[Any, ...]]) -> str:
    """Compute SHA-256 hex digest from a sorted list of tuples."""
    if not tuples:
        return ""
    sorted_tuples = sorted(tuples)
    data = ",".join(":".join(str(v) for v in t) for t in sorted_tuples)
    return hashlib.sha256(data.encode()).hexdigest()


def _node_groups(node: WdmNode) -> dict[int | None, dict[str, Any]]:
    """Split a node's channels and line ports into per-module groups.

    Key None is the device-level group. Each group carries its own fixedness,
    resolved from the module's profile (module groups) or the node (device group).
    """
    from .choices import WdmNodeTypeChoices
    from .models import _module_wdm_profile

    groups: dict[int | None, dict[str, Any]] = {}

    def group(module_id: int | None, module: Any) -> dict[str, Any]:
        if module_id not in groups:
            profile = _module_wdm_profile(module)
            if profile is not None:
                is_fixed = profile.node_type != WdmNodeTypeChoices.ROADM
            else:
                is_fixed = node.is_fixed
            groups[module_id] = {
                "channels": [],
                "tx_rp_ids": [],
                "rx_rp_ids": [],
                "rp_ids": set(),
                "is_fixed": is_fixed,
            }
        return groups[module_id]

    for lp in node.line_ports.select_related("module__module_type"):
        g = group(lp.module_id, lp.module)
        g["rp_ids"].add(lp.rear_port_id)
        if lp.role in (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI):
            g["tx_rp_ids"].append(lp.rear_port_id)
        if lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI):
            g["rx_rp_ids"].append(lp.rear_port_id)

    for ch in node.channels.select_related("module__module_type"):
        group(ch.module_id, ch.module)["channels"].append(ch)

    return groups


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_expected_port_hash(node: WdmNode) -> str:
    """Expected hash: per-module cross-product for fixed groups, position-only for ROADM groups."""
    tuples: list[tuple[Any, ...]] = []
    for module_id, g in _node_groups(node).items():
        mid = module_id or 0
        for ch in g["channels"]:
            if g["is_fixed"]:
                if ch.mux_front_port_id is not None:
                    tuples.extend(("f", mid, ch.mux_front_port_id, rp, ch.grid_position) for rp in g["tx_rp_ids"])
                if ch.demux_front_port_id is not None:
                    tuples.extend(("f", mid, ch.demux_front_port_id, rp, ch.grid_position) for rp in g["rx_rp_ids"])
            else:
                if ch.mux_front_port_id is not None:
                    tuples.append(("r", mid, ch.mux_front_port_id, 0, ch.grid_position))
                if ch.demux_front_port_id is not None:
                    tuples.append(("r", mid, ch.demux_front_port_id, 0, ch.grid_position))
    return _hash_tuples(tuples)


def compute_actual_port_hash(node: WdmNode) -> str:
    """Actual hash from PortMappings, grouped and tagged the same way as the expected hash."""
    tuples: list[tuple[Any, ...]] = []
    for module_id, g in _node_groups(node).items():
        mid = module_id or 0
        fp_ids = set()
        for ch in g["channels"]:
            if ch.mux_front_port_id is not None:
                fp_ids.add(ch.mux_front_port_id)
            if ch.demux_front_port_id is not None:
                fp_ids.add(ch.demux_front_port_id)
        if not fp_ids or not g["rp_ids"]:
            continue
        mappings = PortMapping.objects.filter(
            device=node.device,
            front_port_id__in=fp_ids,
            rear_port_id__in=g["rp_ids"],
        ).values_list("front_port_id", "rear_port_id", "rear_port_position")
        if g["is_fixed"]:
            tuples.extend(("f", mid, fp, rp, pos) for fp, rp, pos in mappings)
        else:
            tuples.extend(("r", mid, fp, 0, pos) for fp, pos in {(fp, pos) for fp, _, pos in mappings})
    return _hash_tuples(tuples)


def check_port_sync(node: WdmNode) -> bool:
    """Check if the node's port mappings are in sync. Returns True if in sync."""
    expected = compute_expected_port_hash(node)
    actual = compute_actual_port_hash(node)
    return expected == actual


# ---------------------------------------------------------------------------
# Diff and sync
# ---------------------------------------------------------------------------


def _build_expected_mappings(node: WdmNode) -> set[tuple[int, int, int]]:
    """Build expected (front_port_id, rear_port_id, grid_position) tuples for fixed groups.

    Each fixed group (module-scoped or device-level) contributes its own
    cross-product of channels x that group's own TX/RX line ports. ROADM groups
    are excluded here; they are handled by `_compute_roadm_position_errors`.
    """
    expected: set[tuple[int, int, int]] = set()
    for g in _node_groups(node).values():
        if not g["is_fixed"]:
            continue
        for ch in g["channels"]:
            if ch.mux_front_port_id is not None:
                expected.update((ch.mux_front_port_id, rp_id, ch.grid_position) for rp_id in g["tx_rp_ids"])
            if ch.demux_front_port_id is not None:
                expected.update((ch.demux_front_port_id, rp_id, ch.grid_position) for rp_id in g["rx_rp_ids"])
    return expected


def _build_actual_mappings(node: WdmNode) -> set[tuple[int, int, int]]:
    """Build the set of actual (front_port_id, rear_port_id, rear_port_position) tuples.

    Only considers PortMappings for fixed groups' own WdmChannel front ports and
    WdmLinePort rear ports, scoped per group so cross-module pairs never match.
    """
    actual: set[tuple[int, int, int]] = set()
    for g in _node_groups(node).values():
        if not g["is_fixed"]:
            continue
        fp_ids: set[int] = set()
        for ch in g["channels"]:
            if ch.mux_front_port_id is not None:
                fp_ids.add(ch.mux_front_port_id)
            if ch.demux_front_port_id is not None:
                fp_ids.add(ch.demux_front_port_id)
        if not fp_ids or not g["rp_ids"]:
            continue
        mappings = PortMapping.objects.filter(
            device=node.device,
            front_port_id__in=fp_ids,
            rear_port_id__in=g["rp_ids"],
        ).values_list("front_port_id", "rear_port_id", "rear_port_position")
        actual.update((fp, rp, pos) for fp, rp, pos in mappings)
    return actual


def _compute_roadm_position_errors(node: WdmNode) -> tuple[set[tuple[int, int, int]], set[tuple[int, int, int]]]:
    """For ROADM groups: find PortMappings with wrong positions.

    Operates only on non-fixed groups' channels, scoped per group. Returns
    (to_delete, to_recreate) — mappings that have the wrong rear_port_position
    and the corrected versions to recreate.
    """
    to_delete: set[tuple[int, int, int]] = set()
    to_recreate: set[tuple[int, int, int]] = set()
    for g in _node_groups(node).values():
        if g["is_fixed"]:
            continue
        fp_ids: set[int] = set()
        fp_to_grid: dict[int, int] = {}
        for ch in g["channels"]:
            if ch.mux_front_port_id is not None:
                fp_ids.add(ch.mux_front_port_id)
                fp_to_grid[ch.mux_front_port_id] = ch.grid_position
            if ch.demux_front_port_id is not None:
                fp_ids.add(ch.demux_front_port_id)
                fp_to_grid[ch.demux_front_port_id] = ch.grid_position
        if not fp_ids or not g["rp_ids"]:
            continue
        mappings = PortMapping.objects.filter(
            device=node.device,
            front_port_id__in=fp_ids,
            rear_port_id__in=g["rp_ids"],
        ).values_list("front_port_id", "rear_port_id", "rear_port_position")
        for fp_id, rp_id, pos in mappings:
            expected_pos = fp_to_grid.get(fp_id)
            if expected_pos is not None and pos != expected_pos:
                to_delete.add((fp_id, rp_id, pos))
                to_recreate.add((fp_id, rp_id, expected_pos))

    return to_delete, to_recreate


def compute_sync_diff(node: WdmNode) -> dict[str, Any]:
    """Compute the full diff between expected and actual port state, per group.

    Fixed groups: full set comparison of expected vs actual mappings, scoped to
    that group's own line ports. ROADM groups: only detect wrong-position
    mappings (direction assignment is dynamic). A node's groups may mix both.
    """
    from dcim.models import FrontPort, FrontPortTemplate, RearPortTemplate

    expected = _build_expected_mappings(node)
    actual = _build_actual_mappings(node)
    to_create = expected - actual
    to_delete = actual - expected
    roadm_to_delete, roadm_to_recreate = _compute_roadm_position_errors(node)
    to_delete |= roadm_to_delete
    to_create |= roadm_to_recreate

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
    affected_circuits = list(
        WdmCircuit.objects.filter(wavelength_paths__id__in=path_ids).distinct().values("id", "name")
    )

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

        # Phase 2: PortMapping repair, per group (fixed groups get a full reset,
        # ROADM groups only get their wrong-position mappings corrected)
        expected = _build_expected_mappings(node)
        actual = _build_actual_mappings(node)
        to_create = expected - actual
        to_delete = actual - expected
        roadm_to_delete, roadm_to_recreate = _compute_roadm_position_errors(node)
        to_delete |= roadm_to_delete
        to_create |= roadm_to_recreate

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
