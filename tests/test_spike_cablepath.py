"""Spike experiments for delegating wavelength traversal to core CablePath.

Provenance: issue #44 spike. These tests are experiments demonstrating how
core ``CablePath.from_origin`` behaves against WDM plants under two cable
modeling schemes:

- strand-space profiles (current builders: trunk-2c1p / single-1c1p, cable
  positions identify physical fibres), and
- channel-space profiles (connector position count covers the trunk rear
  port's channel slots, so cable positions ARE channel positions).

Core's position_stack treats PortMapping rear/front positions and cable
connector positions as one namespace: the position popped at a profiled
cable hop is whatever the previous PortMapping pushed. Under strand-space
profiles a channel position therefore cannot survive a cable hop; under
channel-space profiles the whole walk works, including with completely dark
client edges.
"""

from __future__ import annotations

import pytest
from dcim.choices import CableProfileChoices
from dcim.models import Cable, Device, DeviceType, FrontPort, Interface, RearPort
from dcim.utils import path_node_to_object

from netbox_wdm.core_walk import trace_segment_from_rear_port
from netbox_wdm.testing import create_duplex_mux, create_patch_panel, duplex_mux_pair


def _decompiled(path):
    """Decompile an (unsaved) CablePath's node groups into model instances."""
    return [[path_node_to_object(node) for node in group] for group in path.path]


def _fp(device, name):
    return FrontPort.objects.get(device=device, name=name)


def _rp(device, name):
    return RearPort.objects.get(device=device, name=name)


def _cable_channel_space(mux_a, pp_a, pp_b, mux_b):
    """Duplex A<->B run through a PP pair using channel-space profiles.

    Same physical shape as cable_duplex_through_pp_pair (3 duplex cables,
    2 strands each) but with trunk-2c12p so each strand-connector carries 12
    positions -- enough to cover the 8-channel CWDM mux's 10 rear port slots
    (8 channels + EXP + 1310). Cable positions are channel positions.
    """
    a_patch = Cable(
        profile=CableProfileChoices.TRUNK_2C12P,
        status="connected",
        label="CS A-patch",
        a_terminations=[mux_a.line_ports["tx"].rear_port, mux_a.line_ports["rx"].rear_port],
        b_terminations=[_fp(pp_a, "FP-01"), _fp(pp_a, "FP-02")],
    )
    a_patch.save()
    trunk = Cable(
        profile=CableProfileChoices.TRUNK_2C12P,
        status="connected",
        label="CS trunk",
        a_terminations=[_rp(pp_a, "RP-01"), _rp(pp_a, "RP-02")],
        b_terminations=[_rp(pp_b, "RP-01"), _rp(pp_b, "RP-02")],
    )
    trunk.save()
    b_patch = Cable(
        profile=CableProfileChoices.TRUNK_2C12P,
        status="connected",
        label="CS B-patch",
        a_terminations=[_fp(pp_b, "FP-01"), _fp(pp_b, "FP-02")],
        b_terminations=[mux_b.line_ports["rx"].rear_port, mux_b.line_ports["tx"].rear_port],
    )
    b_patch.save()
    return a_patch, trunk, b_patch


@pytest.fixture
def channel_space_plant(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
    """Two duplex CWDM muxes joined via PP pair with channel-space cables.

    No client-side cabling exists anywhere: every channel is provisioned
    but dark.
    """
    mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "CS-MUX-A")
    mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "CS-MUX-B")
    pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "CS-PP-A")
    pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "CS-PP-B")
    cables = _cable_channel_space(mux_a, pp_a, pp_b, mux_b)
    return {"mux_a": mux_a, "mux_b": mux_b, "pp_a": pp_a, "pp_b": pp_b, "cables": cables}


@pytest.mark.django_db(transaction=True)
class TestStrandSpaceProfiles:
    """Core from_origin against the current builders' strand-space cabling."""

    def test_native_interface_trace_stops_at_trunk(self, wdm_site, wdm_manufacturer, dt_cwdm_dx, dt_pp, wdm_roles):
        """Core's own CablePath from a cabled client interface dies at the
        first strand-space trunk cable: the channel position pushed by the
        mux's PortMapping cannot match the trunk termination's cable
        positions ([1]), so peer resolution returns None."""
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        mux_a = topo.bundles["mux_a"]

        dt_xpdr = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="XPDR", slug="xpdr")
        xpdr = Device.objects.create(name="XPDR-1", site=wdm_site, device_type=dt_xpdr, role=wdm_roles["wdm-mux"])
        iface = Interface.objects.create(device=xpdr, name="xe-0/0/0", type="10gbase-x-sfpp")

        ch3 = next(ch for ch in mux_a.channels if ch.grid_position == 3)
        Cable(
            profile=CableProfileChoices.SINGLE_1C1P,
            status="connected",
            a_terminations=[iface],
            b_terminations=[ch3.mux_front_port],
        ).save()

        cable_path = Interface.objects.get(pk=iface.pk).path
        assert cable_path is not None
        assert cable_path.is_complete is False

        nodes = [obj for group in _decompiled(cable_path) for obj in group]
        # The walk enters the mux and reaches the COM-TX rear port...
        assert mux_a.line_ports["tx"].rear_port in nodes
        # ...but never crosses the trunk cable onto the patch panel.
        pp_a = topo.patch_panels[0]
        assert not any(getattr(obj, "device", None) == pp_a for obj in nodes)

    def test_seeded_walk_cannot_select_channel(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        """Seeding channel 3 at the COM-TX rear port dies at the first cable
        hop (position 3 does not exist on a trunk-2c1p connector), while
        seeding position 1 walks the physical strand but exits the far COM-RX
        at PortMapping position 1 -- always CH1-DEMUX, regardless of which
        channel was meant. Strand positions and channel slots do not commute."""
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        mux_a = topo.bundles["mux_a"]
        mux_b = topo.bundles["mux_b"]
        com_tx = mux_a.line_ports["tx"].rear_port

        dead = trace_segment_from_rear_port(com_tx, 3)
        dead_nodes = [obj for group in _decompiled(dead) for obj in group]
        assert not any(isinstance(obj, FrontPort) for obj in dead_nodes)

        strand = trace_segment_from_rear_port(com_tx, 1)
        last_group = _decompiled(strand)[-1]
        assert last_group == [_fp(mux_b.device, "CH1-DEMUX")]


@pytest.mark.django_db(transaction=True)
class TestChannelSpaceProfiles:
    """Core from_origin against channel-space cabling (positions are channels)."""

    def test_dark_channel_walk_reaches_far_demux(self, channel_space_plant):
        """A trunk-RearPort origin seeded with channel 3 walks the full run
        and lands on the far mux's CH3-DEMUX with NOTHING cabled at either
        client edge (provisioned-but-dark capacity)."""
        plant = channel_space_plant
        com_tx = plant["mux_a"].line_ports["tx"].rear_port

        path = trace_segment_from_rear_port(com_tx, 3)
        assert path is not None
        assert path.pk is None  # ephemeral: never saved
        assert path.is_active is True

        groups = _decompiled(path)
        assert groups[-1] == [_fp(plant["mux_b"].device, "CH3-DEMUX")]

    def test_each_position_reaches_its_own_client_port(self, channel_space_plant):
        """Channel slots 1..8 land on their own DEMUX; slot 9 lands on the
        EXP-DEMUX pass-through port occupying the position after the channels."""
        plant = channel_space_plant
        com_tx = plant["mux_a"].line_ports["tx"].rear_port
        mux_b_dev = plant["mux_b"].device

        for pos, name in ((1, "CH1-DEMUX"), (5, "CH5-DEMUX"), (8, "CH8-DEMUX"), (9, "EXP-DEMUX")):
            path = trace_segment_from_rear_port(com_tx, pos)
            assert _decompiled(path)[-1] == [_fp(mux_b_dev, name)], f"position {pos}"

    def test_reverse_direction_walk(self, channel_space_plant):
        """Seeding at the far mux's COM-TX follows the return strand
        (connector 2 throughout) back to the near mux's DEMUX."""
        plant = channel_space_plant
        com_tx_b = plant["mux_b"].line_ports["tx"].rear_port

        path = trace_segment_from_rear_port(com_tx_b, 4)
        assert _decompiled(path)[-1] == [_fp(plant["mux_a"].device, "CH4-DEMUX")]

    def test_walk_structure_maps_to_d3_segment_items(self, channel_space_plant):
        """The node-group sequence is exactly the port/cable alternation the
        D3 builder's CableSegmentItem list needs: RP, cable, FP, RP, cable,
        RP, FP, cable, RP, FP."""
        plant = channel_space_plant
        path = trace_segment_from_rear_port(plant["mux_a"].line_ports["tx"].rear_port, 2)

        kinds = [type(group[0]).__name__ for group in _decompiled(path)]
        assert kinds == [
            "RearPort",  # MUX-A COM-TX
            "Cable",  # A-patch
            "FrontPort",  # PP-A FP-01
            "RearPort",  # PP-A RP-01
            "Cable",  # trunk
            "RearPort",  # PP-B RP-01
            "FrontPort",  # PP-B FP-01
            "Cable",  # B-patch
            "RearPort",  # MUX-B COM-RX
            "FrontPort",  # MUX-B CH2-DEMUX
        ]

    def test_is_active_reflects_cable_status(self, channel_space_plant):
        """Core derives is_active from cable statuses along the walk, which
        replaces the plugin's own re-derivation in trace_wavelength_path."""
        plant = channel_space_plant
        trunk = plant["cables"][1]
        Cable.objects.filter(pk=trunk.pk).update(status="planned")

        path = trace_segment_from_rear_port(plant["mux_a"].line_ports["tx"].rear_port, 3)
        assert path.is_active is False
        # The walk itself still completes to the far DEMUX.
        assert _decompiled(path)[-1] == [_fp(plant["mux_b"].device, "CH3-DEMUX")]
