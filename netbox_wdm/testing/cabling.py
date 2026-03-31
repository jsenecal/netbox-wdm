"""Cabling helpers for WDM test topologies.

Provides functions that create standard patch-panel pass-through cable runs
used in fiber plant test fixtures.
"""

from __future__ import annotations

from dcim.models import Cable, Device, FrontPort, RearPort


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
) -> tuple[Cable, Cable, Cable]:
    """Create a 3-cable pass-through run via a pair of patch panels.

    Creates:
        1. device_a_rearport → PP-A FP-{nn}  (patch cable)
        2. PP-A RP-{nn} → PP-B RP-{nn}       (trunk cable)
        3. PP-B FP-{nn} → device_b_rearport   (patch cable)

    Returns:
        tuple of (patch_cable_1, trunk_cable, patch_cable_2)
    """
    pp_a_fp = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num:02d}")
    pp_a_rp = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num:02d}")
    pp_b_fp = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num:02d}")
    pp_b_rp = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num:02d}")

    sep = " " if label_prefix else ""

    patch_cable_1 = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}A-patch",
        a_terminations=[device_a_rearport],
        b_terminations=[pp_a_fp],
    )
    patch_cable_1.save()

    trunk_cable = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}trunk",
        a_terminations=[pp_a_rp],
        b_terminations=[pp_b_rp],
    )
    trunk_cable.save()

    patch_cable_2 = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}B-patch",
        a_terminations=[pp_b_fp],
        b_terminations=[device_b_rearport],
    )
    patch_cable_2.save()

    return (patch_cable_1, trunk_cable, patch_cable_2)


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
) -> tuple[Cable, Cable, Cable]:
    """Create 3 duplex cables for a bidirectional link through patch panels.

    Each cable carries both TX and RX fibres as a multi-terminated pair:
        1. A-patch: [A.COM-TX, A.COM-RX] → PP-A [FP-nn, FP-nn+1]
        2. Trunk:   PP-A [RP-nn, RP-nn+1] → PP-B [RP-nn, RP-nn+1]
        3. B-patch: PP-B [FP-nn, FP-nn+1] → [B.COM-RX, B.COM-TX]

    Uses consecutive PP port pairs (port_num and port_num + 1).

    Returns:
        tuple of (a_patch, trunk, b_patch)
    """
    # PP-A ports: TX fibre on port_num, RX fibre on port_num + 1
    pp_a_fp_tx = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num:02d}")
    pp_a_fp_rx = FrontPort.objects.get(device=pp_a_device, name=f"FP-{pp_a_port_num + 1:02d}")
    pp_a_rp_tx = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num:02d}")
    pp_a_rp_rx = RearPort.objects.get(device=pp_a_device, name=f"RP-{pp_a_port_num + 1:02d}")

    # PP-B ports
    pp_b_fp_tx = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num:02d}")
    pp_b_fp_rx = FrontPort.objects.get(device=pp_b_device, name=f"FP-{pp_b_port_num + 1:02d}")
    pp_b_rp_tx = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num:02d}")
    pp_b_rp_rx = RearPort.objects.get(device=pp_b_device, name=f"RP-{pp_b_port_num + 1:02d}")

    sep = " " if label_prefix else ""

    a_patch = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}A-patch",
        a_terminations=[device_a_tx_rp, device_a_rx_rp],
        b_terminations=[pp_a_fp_tx, pp_a_fp_rx],
    )
    a_patch.save()

    trunk = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}trunk",
        a_terminations=[pp_a_rp_tx, pp_a_rp_rx],
        b_terminations=[pp_b_rp_tx, pp_b_rp_rx],
    )
    trunk.save()

    b_patch = Cable(
        type=cable_type,
        status=status,
        label=f"{label_prefix}{sep}B-patch",
        a_terminations=[pp_b_fp_tx, pp_b_fp_rx],
        b_terminations=[device_b_rx_rp, device_b_tx_rp],
    )
    b_patch.save()

    return (a_patch, trunk, b_patch)
