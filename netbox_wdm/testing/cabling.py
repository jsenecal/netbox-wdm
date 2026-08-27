"""Cabling helpers for WDM test topologies.

Provides functions that create standard patch-panel pass-through cable runs
used in fiber plant test fixtures.

Every cable is created with a ``Cable.profile`` so NetBox persists the
strand pairing on each ``CableTermination`` (connector/positions) and
``link_peers`` can resolve the far end of each strand explicitly.
"""

from __future__ import annotations

from dcim.choices import CableProfileChoices
from dcim.models import Cable, Device, FrontPort, RearPort


def simplex_cable(
    a_termination,
    b_termination,
    *,
    label: str = "",
    cable_type: str = "smf-os2",
    status: str = "connected",
    color: str = "",
    profile: str = CableProfileChoices.SINGLE_1C1P,
) -> Cable:
    """Create one single-strand cable, profiled ``single-1c1p`` by default.

    Terminations may be any cabled object -- front port, rear port, or
    circuit termination -- so the same helper wires patch runs and carrier
    handoffs alike.

    Pass ``profile=""`` for an unprofiled cable. A single-strand cable has
    no strand ambiguity either way, so this only chooses which branch of
    core's walker the fixture exercises: profiled resolves through the
    connector map, unprofiled takes the positionless legacy path.
    """
    cable = Cable(
        type=cable_type,
        profile=profile,
        status=status,
        color=color,
        label=label,
        a_terminations=[a_termination],
        b_terminations=[b_termination],
    )
    cable.save()
    return cable


def cable_through_pp_pair(
    device_a_rearport: RearPort,
    pp_a_device: Device,
    pp_b_device: Device,
    device_b_rearport: RearPort,
    *,
    pp_a_port_num: int = 1,
    pp_b_port_num: int = 1,
    label_prefix: str = "",
    cable_type: str = "smf-os2",
    status: str = "connected",
    patch_color: str = "",
    trunk_color: str = "",
) -> tuple[Cable, Cable, Cable]:
    """Create a 3-cable pass-through run via a pair of patch panels.

    Creates:
        1. device_a_rearport → PP-A FP-{nn}  (patch cable)
        2. PP-A RP-{nn} → PP-B RP-{nn}       (trunk cable)
        3. PP-B FP-{nn} → device_b_rearport   (patch cable)

    All three cables carry the ``single-1c1p`` profile (one connector,
    one position per side).

    Returns:
        tuple of (patch_cable_1, trunk_cable, patch_cable_2)
    """
    pp_a_fp = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num:02d}")
    pp_a_rp = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num:02d}")
    pp_b_fp = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num:02d}")
    pp_b_rp = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num:02d}")

    sep = " " if label_prefix else ""

    def _leg(a, b, name: str, color: str) -> Cable:
        return simplex_cable(
            a, b, label=f"{label_prefix}{sep}{name}", cable_type=cable_type, status=status, color=color
        )

    return (
        _leg(device_a_rearport, pp_a_fp, "A-patch", patch_color),
        _leg(pp_a_rp, pp_b_rp, "trunk", trunk_color),
        _leg(pp_b_fp, device_b_rearport, "B-patch", patch_color),
    )


def cable_duplex_through_pp_pair(
    device_a_tx_rp: RearPort,
    device_a_rx_rp: RearPort,
    pp_a_device: Device,
    pp_b_device: Device,
    device_b_rx_rp: RearPort,
    device_b_tx_rp: RearPort,
    *,
    pp_a_port_num: int = 1,
    pp_b_port_num: int = 1,
    label_prefix: str = "",
    cable_type: str = "smf-os2",
    status: str = "connected",
    patch_color: str = "",
    trunk_color: str = "",
) -> tuple[Cable, Cable, Cable]:
    """Create 3 duplex cables for a bidirectional link through patch panels.

    Each cable carries both TX and RX fibres as a multi-terminated pair:
        1. A-patch: [A.COM-TX, A.COM-RX] → PP-A [FP-nn, FP-nn+1]
        2. Trunk:   PP-A [RP-nn, RP-nn+1] → PP-B [RP-nn, RP-nn+1]
        3. B-patch: PP-B [FP-nn, FP-nn+1] → [B.COM-RX, B.COM-TX]

    Uses consecutive PP port pairs (port_num and port_num + 1).

    All three cables carry the ``trunk-2c1p`` profile (two connectors, one
    position each), so each strand keeps its own connector and the TX and
    RX fibres are paired explicitly rather than by termination order.

    Returns:
        tuple of (a_patch, trunk, b_patch)
    """
    pp_a_fp_tx = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num:02d}")
    pp_a_fp_rx = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num + 1:02d}")
    pp_a_rp_tx = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num:02d}")
    pp_a_rp_rx = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num + 1:02d}")

    pp_b_fp_tx = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num:02d}")
    pp_b_fp_rx = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num + 1:02d}")
    pp_b_rp_tx = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num:02d}")
    pp_b_rp_rx = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num + 1:02d}")

    sep = " " if label_prefix else ""

    def _leg(a_terms: list, b_terms: list, name: str, color: str) -> Cable:
        cable = Cable(
            type=cable_type,
            profile=CableProfileChoices.TRUNK_2C1P,
            status=status,
            color=color,
            label=f"{label_prefix}{sep}{name}",
            a_terminations=a_terms,
            b_terminations=b_terms,
        )
        cable.save()
        return cable

    return (
        _leg([device_a_tx_rp, device_a_rx_rp], [pp_a_fp_tx, pp_a_fp_rx], "A-patch", patch_color),
        _leg([pp_a_rp_tx, pp_a_rp_rx], [pp_b_rp_tx, pp_b_rp_rx], "trunk", trunk_color),
        _leg([pp_b_fp_tx, pp_b_fp_rx], [device_b_rx_rp, device_b_tx_rp], "B-patch", patch_color),
    )
