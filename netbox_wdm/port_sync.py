"""Port sync detection and repair for WDM nodes.

Computes expected vs actual PortMapping state and provides sync operations.

The expected PortMapping state is derived from WdmChannel and WdmLinePort data:
  - Each channel's mux_front_port maps to TX (or BIDI) line port rear ports.
  - Each channel's demux_front_port maps to RX (or BIDI) line port rear ports.

The actual PortMapping state is read from PortMapping rows, filtered to only those
whose front_port belongs to a WdmChannel on this node. Hashes of sorted
(fp_id, rp_id, grid_position) tuples are compared to detect sync drift.

Note: NetBox auto-creates PortMappings from PortTemplateMappings when a Device is
instantiated. This module verifies that WdmChannel data is consistent with those
auto-created mappings. Extra PortMappings (e.g., EXP/1310 pass-through ports) that
are not part of any WdmChannel are intentionally excluded from both hashes.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from dcim.models import PortMapping

from .choices import WdmLineRoleChoices

if TYPE_CHECKING:
    from .models import WdmNode


def _hash_tuples(tuples: list[tuple[int, int, int]]) -> str:
    """Compute SHA-256 hex digest from a sorted list of (front_port_id, rear_port_id, position) tuples."""
    if not tuples:
        return ""
    sorted_tuples = sorted(tuples)
    data = ",".join(f"{fp}:{rp}:{pos}" for fp, rp, pos in sorted_tuples)
    return hashlib.sha256(data.encode()).hexdigest()


def compute_expected_port_hash(node: WdmNode) -> str:
    """Compute the hash of the expected PortMapping state from WdmChannels and WdmLinePorts.

    For duplex nodes: mux_front_port → TX line ports, demux_front_port → RX line ports.
    For single-fiber nodes: both mux and demux front ports → BIDI line ports.

    Returns an empty string if there are no line ports or no channels with front ports.
    """
    line_ports = list(node.line_ports.select_related("rear_port").order_by("direction", "role"))
    if not line_ports:
        return ""

    tx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.TX, WdmLineRoleChoices.BIDI)]
    rx_rp_ids = [lp.rear_port_id for lp in line_ports if lp.role in (WdmLineRoleChoices.RX, WdmLineRoleChoices.BIDI)]

    channels = node.channels.order_by("grid_position")
    tuples: list[tuple[int, int, int]] = []
    for ch in channels:
        if ch.mux_front_port_id is not None:
            for rp_id in tx_rp_ids:
                tuples.append((ch.mux_front_port_id, rp_id, ch.grid_position))
        if ch.demux_front_port_id is not None:
            for rp_id in rx_rp_ids:
                tuples.append((ch.demux_front_port_id, rp_id, ch.grid_position))

    return _hash_tuples(tuples)


def compute_actual_port_hash(node: WdmNode) -> str:
    """Compute the hash of the actual PortMapping state on the device.

    Only considers PortMappings whose front_port belongs to a WdmChannel on this node,
    and whose rear_port is a WdmLinePort rear port. Uses rear_port_position as the
    grid position dimension.
    """
    line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
    if not line_port_rp_ids:
        return ""

    # Collect all front_port_ids from WdmChannels (mux and demux, excluding None)
    channel_fp_ids: set[int] = set()
    for ch in node.channels.all():
        if ch.mux_front_port_id is not None:
            channel_fp_ids.add(ch.mux_front_port_id)
        if ch.demux_front_port_id is not None:
            channel_fp_ids.add(ch.demux_front_port_id)

    if not channel_fp_ids:
        return ""

    mappings = (
        PortMapping.objects.filter(
            device=node.device,
            front_port_id__in=channel_fp_ids,
            rear_port_id__in=line_port_rp_ids,
        )
        .values_list("front_port_id", "rear_port_id", "rear_port_position")
        .order_by("front_port_id", "rear_port_id", "rear_port_position")
    )
    tuples = [(fp, rp, pos) for fp, rp, pos in mappings]
    return _hash_tuples(tuples)


def check_port_sync(node: WdmNode) -> bool:
    """Check if the node's port mappings are in sync. Returns True if in sync."""
    expected = compute_expected_port_hash(node)
    actual = compute_actual_port_hash(node)
    return expected == actual
