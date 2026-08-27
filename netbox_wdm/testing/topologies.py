"""Pre-built WDM topologies for testing and sample data.

Each topology creates all devices, patch panels, cables, and WDM objects.
All inter-device links go through patch panel pairs.

Topologies:
1. duplex_mux_pair      - DX-MUX <-> PP pair <-> DX-MUX
2. sf_mux_pair          - SF-MUX <-> PP pair <-> SF-MUX
3. dwdm_mux_to_roadm   - DWDM-MUX <-> PP pair <-> ROADM
4. mux_roadm_mux       - DX-MUX <-> PP pair <-> ROADM <-> PP pair <-> DX-MUX
5. modular_chassis_span - 2-cassette chassis <-> PP pairs <-> 2 single-cassette chassis
6. cascaded_pp_chain    - SF-MUX <-> N panels cascaded rear-to-front <-> SF-MUX
7. midspan_circuit_span - SF-MUX <-> PP <-> carrier circuit <-> PP <-> SF-MUX
"""

from __future__ import annotations

from dataclasses import dataclass

from circuits.models import Circuit, CircuitTermination, CircuitType, Provider
from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, FrontPortTemplate, ModuleType, RearPort, Site
from django.db import transaction

from .cabling import cable_duplex_through_pp_pair, cable_through_pp_pair, simplex_cable
from .devices import WdmDeviceBundle, create_duplex_mux, create_patch_panel, create_roadm, create_sf_mux


@dataclass
class Topology:
    """Container for a complete topology's objects."""

    name: str
    bundles: dict[str, WdmDeviceBundle]
    patch_panels: list[Device]
    cables: list[Cable]
    circuit: Circuit | None = None


@transaction.atomic
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


@transaction.atomic
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


@transaction.atomic
def sf_mux_long_chain(
    site: Site,
    dt_sf_mux: DeviceType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    passthrough_units: int,
    name_prefix: str = "",
) -> Topology:
    """Create two SF MUX endpoints joined by a long chain of patch panel pass-throughs.

    Each pass-through unit occupies three patch panel ports (A, B, C) wired so
    that the trace walker consumes one discovery hop per unit:

        ...RP ->(patch)-> A.FP =PM= A.RP ->(trunk)-> B.RP =PM= B.FP ->(patch)-> C.FP =PM= C.RP...

    A terminal patch panel port pair then patches into the far MUX COM rear
    port, costing one more hop, so discovering the far end takes
    passthrough_units + 1 hops. Patch panel devices are created as needed;
    ports are allocated sequentially across them.

    Args:
        site: Site instance for all devices.
        dt_sf_mux: DeviceType for single-fiber MUX devices.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux" and "fiber-pp" mapping to DeviceRole instances.
        passthrough_units: Number of three-port pass-through units in the chain.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux_a" and "mux_b".
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-A")
    mux_b = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-B")

    ports_needed = 3 * passthrough_units + 2
    ports_per_panel = FrontPortTemplate.objects.filter(device_type=dt_pp).count()
    num_panels = -(-ports_needed // ports_per_panel)
    panels = [create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-{i:02d}") for i in range(1, num_panels + 1)]

    def pp_port(index: int) -> tuple[FrontPort, RearPort]:
        device = panels[index // ports_per_panel]
        num = index % ports_per_panel + 1
        fp = FrontPort.objects.get(device=device, name=f"FP-{num:02d}")
        rp = RearPort.objects.get(device=device, name=f"RP-{num:02d}")
        return fp, rp

    cables: list[Cable] = []

    def add_cable(a_term, b_term, label: str) -> None:
        # Deliberately unprofiled: a single-strand cable has no strand ambiguity,
        # so this chain exercises core's positionless walk branch.
        cables.append(simplex_cable(a_term, b_term, label=label, profile=""))

    current_rp = mux_a.line_ports["bidi"].rear_port
    idx = 0
    for unit in range(1, passthrough_units + 1):
        a_fp, a_rp = pp_port(idx)
        b_fp, b_rp = pp_port(idx + 1)
        c_fp, c_rp = pp_port(idx + 2)
        idx += 3
        add_cable(current_rp, a_fp, f"{p}chain unit {unit} entry")
        add_cable(a_rp, b_rp, f"{p}chain unit {unit} trunk")
        add_cable(b_fp, c_fp, f"{p}chain unit {unit} link")
        current_rp = c_rp

    end_a_fp, end_a_rp = pp_port(idx)
    end_b_fp, end_b_rp = pp_port(idx + 1)
    add_cable(current_rp, end_a_fp, f"{p}chain end entry")
    add_cable(end_a_rp, end_b_rp, f"{p}chain end trunk")
    add_cable(end_b_fp, mux_b.line_ports["bidi"].rear_port, f"{p}chain end exit")

    return Topology(
        name=f"{p}sf-mux-long-chain",
        bundles={"mux_a": mux_a, "mux_b": mux_b},
        patch_panels=panels,
        cables=cables,
    )


@transaction.atomic
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


@transaction.atomic
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


@transaction.atomic
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


@transaction.atomic
def cascaded_pp_chain(
    site: Site,
    dt_sf_mux: DeviceType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    panels: int = 3,
    name_prefix: str = "",
) -> Topology:
    """Create two SF MUX endpoints joined by patch panels cascaded rear-to-front.

    Unlike the rear-to-rear trunks of ``cable_through_pp_pair``, each panel's
    rear port patches into the *front* port of the next panel:

        MUX-A.COM ->(patch)-> PP-1.FP =PM= PP-1.RP ->(patch)-> PP-2.FP =PM= ...
        ... PP-N.RP ->(patch)-> MUX-B.COM

    Both cabling permutations appear in one run, so a walker that only knows
    rear-to-rear trunks cannot reach the far end.

    Args:
        site: Site instance for all devices.
        dt_sf_mux: DeviceType for single-fiber MUX devices.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux" and "fiber-pp" mapping to DeviceRole instances.
        panels: Number of cascaded patch panels between the two MUX devices.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux_a" and "mux_b".
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-A")
    mux_b = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-B")
    pps = [create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-{i}") for i in range(1, panels + 1)]

    cables: list[Cable] = []
    current = mux_a.line_ports["bidi"].rear_port
    for i, pp in enumerate(pps, start=1):
        fp = FrontPort.objects.get(device=pp, name="FP-01")
        cables.append(simplex_cable(current, fp, label=f"{p}cascade {i} in", color="f5e960"))
        current = RearPort.objects.get(device=pp, name="RP-01")
    cables.append(simplex_cable(current, mux_b.line_ports["bidi"].rear_port, label=f"{p}cascade out", color="f5e960"))

    return Topology(
        name=f"{p}cascaded-pp-chain",
        bundles={"mux_a": mux_a, "mux_b": mux_b},
        patch_panels=pps,
        cables=cables,
    )


@transaction.atomic
def midspan_circuit_span(
    site: Site,
    dt_sf_mux: DeviceType,
    dt_pp: DeviceType,
    roles: dict[str, DeviceRole],
    cid: str = "DF-1001",
    name_prefix: str = "",
) -> Topology:
    """Create two SF MUX endpoints joined by a leased carrier circuit mid-span.

    Models the dark-fiber handoff an operator buys between two sites:

        MUX-A.COM ->(patch)-> PP-A.FP =PM= PP-A.RP ->(cable)-> [ CT-A
        circuit CT-Z ] ->(cable)-> PP-B.RP =PM= PP-B.FP ->(patch)-> MUX-B.COM

    The circuit hop carries no cable of its own -- NetBox joins termination A
    to termination Z internally -- so a walker that only follows cables
    stops at the handoff.

    Args:
        site: Site instance for all devices and both circuit terminations.
        dt_sf_mux: DeviceType for single-fiber MUX devices.
        dt_pp: DeviceType for patch panels.
        roles: Dict with keys "wdm-mux" and "fiber-pp" mapping to DeviceRole instances.
        cid: Circuit ID for the leased span.
        name_prefix: Optional prefix for device names.

    Returns:
        Topology with bundles keyed "mux_a" and "mux_b", and ``circuit`` set.
    """
    p = f"{name_prefix}" if name_prefix else ""

    mux_a = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-A")
    mux_b = create_sf_mux(site, dt_sf_mux, roles["wdm-mux"], f"{p}MUX-B")
    pp_a = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-A")
    pp_b = create_patch_panel(site, dt_pp, roles["fiber-pp"], f"{p}PP-B")

    provider, _ = Provider.objects.get_or_create(slug="carrier", defaults={"name": "Carrier"})
    circuit_type, _ = CircuitType.objects.get_or_create(slug="dark-fiber", defaults={"name": "Dark Fiber"})
    circuit = Circuit.objects.create(cid=f"{p}{cid}", provider=provider, type=circuit_type)
    ct_a = CircuitTermination.objects.create(circuit=circuit, term_side="A", termination=site)
    ct_z = CircuitTermination.objects.create(circuit=circuit, term_side="Z", termination=site)

    cables = [
        simplex_cable(
            mux_a.line_ports["bidi"].rear_port,
            FrontPort.objects.get(device=pp_a, name="FP-01"),
            label=f"{p}A-patch",
            color="f5e960",
        ),
        simplex_cable(RearPort.objects.get(device=pp_a, name="RP-01"), ct_a, label=f"{p}A-handoff", color="4287f5"),
        simplex_cable(ct_z, RearPort.objects.get(device=pp_b, name="RP-01"), label=f"{p}Z-handoff", color="4287f5"),
        simplex_cable(
            FrontPort.objects.get(device=pp_b, name="FP-01"),
            mux_b.line_ports["bidi"].rear_port,
            label=f"{p}B-patch",
            color="f5e960",
        ),
    ]

    return Topology(
        name=f"{p}midspan-circuit-span",
        bundles={"mux_a": mux_a, "mux_b": mux_b},
        patch_panels=[pp_a, pp_b],
        cables=cables,
        circuit=circuit,
    )
