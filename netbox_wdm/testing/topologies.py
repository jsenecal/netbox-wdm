"""Pre-built WDM topologies for testing and sample data.

Each topology creates all devices, patch panels, cables, and WDM objects.
All inter-device links go through patch panel pairs.

Topologies:
1. duplex_mux_pair      - DX-MUX <-> PP pair <-> DX-MUX
2. sf_mux_pair          - SF-MUX <-> PP pair <-> SF-MUX
3. dwdm_mux_to_roadm   - DWDM-MUX <-> PP pair <-> ROADM
4. mux_roadm_mux       - DX-MUX <-> PP pair <-> ROADM <-> PP pair <-> DX-MUX
5. modular_chassis_span - 2-cassette chassis <-> PP pairs <-> 2 single-cassette chassis
"""

from __future__ import annotations

from dataclasses import dataclass

from dcim.models import Cable, Device, DeviceRole, DeviceType, ModuleType, Site

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
        patch_color="f5e960",
        trunk_color="4287f5",
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
        patch_color="f5e960",
        trunk_color="4287f5",
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
        patch_color="f5e960",
        trunk_color="4287f5",
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
        patch_color="f5e960",
        trunk_color="4287f5",
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
        patch_color="f5e960",
        trunk_color="4287f5",
    )

    return Topology(
        name=f"{p}mux-roadm-mux",
        bundles={"mux_a": mux_a, "roadm": roadm, "mux_b": mux_b},
        patch_panels=[pp_ea, pp_eb, pp_wa, pp_wb],
        cables=list(east_cables) + list(west_cables),
    )


def modular_chassis_span(
    site: Site,
    mt_cassette: ModuleType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    name_prefix: str = "",
) -> Topology:
    """A 2-cassette chassis linked to two single-cassette peers through PP pairs."""
    from .devices import create_modular_chassis

    p = f"{name_prefix}" if name_prefix else ""
    hub = create_modular_chassis(site, roles["wdm-mux"], f"{p}CHASSIS-HUB", mt_cassette, bays=("MUX1", "MUX2"))
    peer1 = create_modular_chassis(site, roles["wdm-mux"], f"{p}CHASSIS-P1", mt_cassette, bays=("MUX1",))
    peer2 = create_modular_chassis(site, roles["wdm-mux"], f"{p}CHASSIS-P2", mt_cassette, bays=("MUX1",))

    cables: list[Cable] = []
    panels: list[Device] = []
    for i, (bay, peer) in enumerate((("MUX1", peer1), ("MUX2", peer2)), start=1):
        pp_a = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-M{i}A")
        pp_b = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-M{i}B")
        panels += [pp_a, pp_b]
        cables += cable_duplex_through_pp_pair(
            device_a_tx_rp=hub.node.line_ports.get(module=hub.modules[bay], role="tx").rear_port,
            device_a_rx_rp=hub.node.line_ports.get(module=hub.modules[bay], role="rx").rear_port,
            pp_a_device=pp_a,
            pp_b_device=pp_b,
            device_b_rx_rp=peer.node.line_ports.get(role="rx").rear_port,
            device_b_tx_rp=peer.node.line_ports.get(role="tx").rear_port,
            label_prefix=f"{p}MODSPAN{i}",
        )

    bundles = {
        "hub": WdmDeviceBundle(device=hub.device, node=hub.node, line_ports={}, channels=list(hub.node.channels.all())),
        "peer1": WdmDeviceBundle(
            device=peer1.device, node=peer1.node, line_ports={}, channels=list(peer1.node.channels.all())
        ),
        "peer2": WdmDeviceBundle(
            device=peer2.device, node=peer2.node, line_ports={}, channels=list(peer2.node.channels.all())
        ),
    }
    return Topology(name=f"{p}modular-chassis-span", bundles=bundles, patch_panels=panels, cables=cables)
