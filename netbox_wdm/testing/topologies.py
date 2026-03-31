"""Pre-built WDM topologies for testing and sample data.

Each topology creates all devices, patch panels, cables, and WDM objects.
All inter-device links go through patch panel pairs.

Topologies:
1. duplex_mux_pair      - DX-MUX <-> PP pair <-> DX-MUX
2. sf_mux_pair          - SF-MUX <-> PP pair <-> SF-MUX
3. dwdm_mux_to_roadm   - DWDM-MUX <-> PP pair <-> ROADM
"""

from __future__ import annotations

from dataclasses import dataclass

from dcim.models import Cable, Device, DeviceRole, DeviceType, Site

from .cabling import cable_duplex_through_pp_pair, cable_through_pp_pair
from .devices import WdmDeviceBundle, create_duplex_mux, create_patch_panel, create_roadm, create_sf_mux


@dataclass
class Topology:
    """Container for a complete topology's objects."""

    name: str
    bundles: dict[str, WdmDeviceBundle]
    patch_panels: list[Device]
    cables: list[Cable]


def duplex_mux_pair(
    site: Site, dt_mux: DeviceType, dt_pp: DeviceType, roles: dict[str, DeviceRole], name_prefix: str = ""
) -> Topology:
    """Create a duplex MUX pair topology with patch panel interconnect.

    Creates 2 duplex MUX devices and 2 patch panels, linked by 6 cables
    via cable_duplex_through_pp_pair (TX and RX directions).

    Args:
        site: Site instance for all devices.
        dt_mux: DeviceType for duplex MUX devices.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux" and "fiber-pp" mapping to DeviceRole instances.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux_a" and "mux_b".
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_duplex_mux(site, dt_mux, roles["wdm-mux"], f"{p}MUX-A")
    mux_b = create_duplex_mux(site, dt_mux, roles["wdm-mux"], f"{p}MUX-B")

    pp_a = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-A")
    pp_b = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-B")

    cables = cable_duplex_through_pp_pair(
        device_a_tx_rp=mux_a.line_ports["tx"].rear_port,
        device_a_rx_rp=mux_a.line_ports["rx"].rear_port,
        pp_a_device=pp_a,
        pp_b_device=pp_b,
        device_b_rx_rp=mux_b.line_ports["rx"].rear_port,
        device_b_tx_rp=mux_b.line_ports["tx"].rear_port,
        label_prefix=p.strip("-") if p else "DX",
    )

    return Topology(
        name=f"{p}duplex-mux-pair",
        bundles={"mux_a": mux_a, "mux_b": mux_b},
        patch_panels=[pp_a, pp_b],
        cables=list(cables),
    )


def sf_mux_pair(
    site: Site, dt_sf_mux: DeviceType, dt_pp: DeviceType, roles: dict[str, DeviceRole], name_prefix: str = ""
) -> Topology:
    """Create a single-fiber MUX pair topology with patch panel interconnect.

    Creates 2 SF MUX devices and 2 patch panels, linked by 3 cables
    via cable_through_pp_pair (single direction).

    Args:
        site: Site instance for all devices.
        dt_sf_mux: DeviceType for single-fiber MUX devices.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux" and "fiber-pp" mapping to DeviceRole instances.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux_a" and "mux_b".
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-A")
    mux_b = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-B")

    pp_a = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-A")
    pp_b = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-B")

    cables_tuple = cable_through_pp_pair(
        device_a_rearport=mux_a.line_ports["bidi"].rear_port,
        pp_a_device=pp_a,
        pp_b_device=pp_b,
        device_b_rearport=mux_b.line_ports["bidi"].rear_port,
        label_prefix=p.strip("-") if p else "SF",
    )

    cables = list(cables_tuple)

    return Topology(
        name=f"{p}sf-mux-pair",
        bundles={"mux_a": mux_a, "mux_b": mux_b},
        patch_panels=[pp_a, pp_b],
        cables=cables,
    )


def dwdm_mux_to_roadm(
    site: Site,
    dt_dwdm: DeviceType,
    dt_roadm: DeviceType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    name_prefix: str = "",
) -> Topology:
    """Create a DWDM MUX to ROADM topology with patch panel interconnect.

    Creates 1 DWDM MUX device and 1 ROADM device with 2 patch panels,
    linked by 6 cables via cable_duplex_through_pp_pair (MUX COM-TX/RX
    to ROADM LINE-EAST-RX/TX).

    Args:
        site: Site instance for all devices.
        dt_dwdm: DeviceType for DWDM MUX device.
        dt_roadm: DeviceType for ROADM device.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux", "wdm-roadm", and "fiber-pp" mapping to DeviceRole instances.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux" and "roadm".
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux = create_duplex_mux(site, dt_dwdm, roles["wdm-mux"], f"{p}MUX", grid="dwdm_100ghz")
    roadm = create_roadm(site, dt_roadm, roles["wdm-roadm"], f"{p}ROADM")

    pp_a = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-A")
    pp_b = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-B")

    cables = cable_duplex_through_pp_pair(
        device_a_tx_rp=mux.line_ports["tx"].rear_port,
        device_a_rx_rp=mux.line_ports["rx"].rear_port,
        pp_a_device=pp_a,
        pp_b_device=pp_b,
        device_b_rx_rp=roadm.line_ports["line_east_rx"].rear_port,
        device_b_tx_rp=roadm.line_ports["line_east_tx"].rear_port,
        label_prefix=p.strip("-") if p else "DWDM",
    )

    return Topology(
        name=f"{p}dwdm-mux-to-roadm",
        bundles={"mux": mux, "roadm": roadm},
        patch_panels=[pp_a, pp_b],
        cables=list(cables),
    )


def mux_roadm_mux(
    site: Site,
    dt_dwdm: DeviceType,
    dt_roadm: DeviceType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    name_prefix: str = "",
) -> Topology:
    """Create a MUX → ROADM → MUX pass-through topology.

    MUX-A connects to ROADM EAST side, MUX-B to ROADM WEST side.
    Wavelengths pass through the ROADM (EAST-RX → WEST-TX).

    Creates 3 devices and 4 patch panels, linked by 6 duplex cables.
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_duplex_mux(site, dt_dwdm, roles["wdm-mux"], f"{p}MUX-A", grid="dwdm_100ghz")
    roadm = create_roadm(site, dt_roadm, roles["wdm-roadm"], f"{p}ROADM")
    mux_b = create_duplex_mux(site, dt_dwdm, roles["wdm-mux"], f"{p}MUX-B", grid="dwdm_100ghz")

    pp_ea = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-EA")
    pp_eb = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-EB")
    pp_wa = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-WA")
    pp_wb = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-WB")

    # East side: MUX-A ↔ PPs ↔ ROADM EAST
    east_cables = cable_duplex_through_pp_pair(
        device_a_tx_rp=mux_a.line_ports["tx"].rear_port,
        device_a_rx_rp=mux_a.line_ports["rx"].rear_port,
        pp_a_device=pp_ea,
        pp_b_device=pp_eb,
        device_b_rx_rp=roadm.line_ports["line_east_rx"].rear_port,
        device_b_tx_rp=roadm.line_ports["line_east_tx"].rear_port,
        label_prefix=f"{p.strip('-')} East".strip(),
    )

    # West side: ROADM WEST ↔ PPs ↔ MUX-B
    west_cables = cable_duplex_through_pp_pair(
        device_a_tx_rp=roadm.line_ports["line_west_tx"].rear_port,
        device_a_rx_rp=roadm.line_ports["line_west_rx"].rear_port,
        pp_a_device=pp_wa,
        pp_b_device=pp_wb,
        device_b_rx_rp=mux_b.line_ports["rx"].rear_port,
        device_b_tx_rp=mux_b.line_ports["tx"].rear_port,
        label_prefix=f"{p.strip('-')} West".strip(),
    )

    return Topology(
        name=f"{p}mux-roadm-mux",
        bundles={"mux_a": mux_a, "roadm": roadm, "mux_b": mux_b},
        patch_panels=[pp_ea, pp_eb, pp_wa, pp_wb],
        cables=list(east_cables) + list(west_cables),
    )
