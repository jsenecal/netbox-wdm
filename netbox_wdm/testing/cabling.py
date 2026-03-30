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
    pp_a_tx_port: int = 1,
    pp_b_tx_port: int = 1,
    pp_b_rx_port: int = 2,
    pp_a_rx_port: int = 2,
    label_prefix: str = "",
    cable_type: str = "smf-os2",
    status: str = "connected",
) -> tuple[tuple[Cable, Cable, Cable], tuple[Cable, Cable, Cable]]:
    """Create 6 cables for a duplex link through a pair of patch panels.

    TX direction: A.COM-TX → PP-A → PP-B → B.COM-RX
    RX direction: B.COM-TX → PP-B → PP-A → A.COM-RX

    Returns:
        tuple of (tx_cables, rx_cables) where each is a 3-tuple of
        (patch_cable_1, trunk_cable, patch_cable_2).
    """
    tx_cables = cable_through_pp_pair(
        device_a_tx_rp,
        pp_a_device,
        pp_b_device,
        device_b_rx_rp,
        pp_a_port_num=pp_a_tx_port,
        pp_b_port_num=pp_b_tx_port,
        label_prefix=f"{label_prefix} TX".strip(),
        cable_type=cable_type,
        status=status,
    )

    rx_cables = cable_through_pp_pair(
        device_b_tx_rp,
        pp_b_device,
        pp_a_device,
        device_a_rx_rp,
        pp_a_port_num=pp_b_rx_port,
        pp_b_port_num=pp_a_rx_port,
        label_prefix=f"{label_prefix} RX".strip(),
        cable_type=cable_type,
        status=status,
    )

    return (tx_cables, rx_cables)
