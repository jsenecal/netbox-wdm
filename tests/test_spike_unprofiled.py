"""Spike experiments: position_stack behavior across UNPROFILED cable hops.

Provenance: follow-up to the issue #44 spike (tests/test_spike_cablepath.py),
auditing the issue #58 conclusion that "the cable profile is the ONLY vehicle
that can carry channel identity across a trunk cable".

Mechanism under test (netbox 4.6.8, dcim/models/cables.py, from_origin):

- A cable WITH a profile takes the profiled branch (line 943): it POPS the
  position stack, maps positions through the profile's connector space, and
  PUSHES the mapped positions. Strand-space profiles therefore rewrite a
  channel position into a connector position (the #44 finding).
- A cable WITHOUT a profile takes the legacy branch (line 995): it resolves
  far-end CableTermination rows purely by (cable, opposite cable_end) and
  NEVER touches the position stack. The hop is a pass-through: whatever the
  previous PortMapping pushed survives the cable intact. Unprofiled
  CableTermination rows have connector=None/positions=None (cables.py 492,
  505), so there is also no per-strand discrimination: with multiple
  terminations per end the walk fans out to ALL far-end terminations.
- The seeded dark-channel walk (netbox_wdm.core_walk) relies on the
  profiled branch's empty-stack fallback (line 948) reading the origin's
  in-memory cable_positions. The legacy branch never reads cable_positions,
  so a rear-port-seeded walk cannot cross an unprofiled first hop: it
  reaches the far trunk rear port with an empty stack and aborts
  (line 1072, is_split=True).

These experiments pin down each of those behaviors against real WDM
topologies so the #58 framing can be corrected where it overstates.
"""

from __future__ import annotations

import pytest
from dcim.models import Cable, Device, DeviceType, FrontPort, Interface, RearPort
from dcim.utils import path_node_to_object

from netbox_wdm.core_walk import trace_segment_from_rear_port
from netbox_wdm.testing import create_duplex_mux, create_patch_panel


def _decompiled(path):
    """Decompile an (unsaved) CablePath's node groups into model instances."""
    return [[path_node_to_object(node) for node in group] for group in path.path]


def _flat(path):
    return [obj for group in _decompiled(path) for obj in group]


def _fp(device, name):
    return FrontPort.objects.get(device=device, name=name)


def _rp(device, name):
    return RearPort.objects.get(device=device, name=name)


def _unprofiled(a_terminations, b_terminations, label=""):
    cable = Cable(
        status="connected",
        label=label,
        a_terminations=a_terminations,
        b_terminations=b_terminations,
    )
    cable.save()
    return cable


@pytest.fixture
def mux_pair(wdm_site, dt_cwdm_dx, wdm_roles):
    """Two duplex CWDM muxes, no cabling between them yet."""
    mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "UP-MUX-A")
    mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "UP-MUX-B")
    return mux_a, mux_b


@pytest.fixture
def client_iface(wdm_site, wdm_manufacturer, wdm_roles):
    """A transceiver interface factory (unique device per call)."""
    dt_xpdr, _ = DeviceType.objects.get_or_create(
        manufacturer=wdm_manufacturer, slug="xpdr", defaults={"model": "XPDR"}
    )
    counter = iter(range(1, 100))

    def make(name=None):
        n = next(counter)
        xpdr = Device.objects.create(
            name=name or f"XPDR-{n}", site=wdm_site, device_type=dt_xpdr, role=wdm_roles["wdm-mux"]
        )
        return Interface.objects.create(device=xpdr, name="xe-0/0/0", type="10gbase-x-sfpp")

    return make


@pytest.mark.django_db(transaction=True)
class TestUnprofiledSingleTermination:
    """One termination per cable end: the legacy branch is a pure pass-through."""

    def test_unprofiled_terminations_have_no_connector(self, mux_pair):
        """Documenting the branch condition: unprofiled cables persist
        CableTermination rows with connector=None/positions=None, and
        Cable.profile is empty, so from_origin line 943 selects the legacy
        branch which never reads or writes the position stack."""
        mux_a, mux_b = mux_pair
        trunk = _unprofiled([mux_a.line_ports["tx"].rear_port], [mux_b.line_ports["rx"].rear_port], "UP simplex trunk")
        assert not trunk.profile
        rows = list(trunk.terminations.all())
        assert rows and all(row.connector is None and row.positions is None for row in rows)

    def test_native_trace_preserves_channel_and_completes(self, mux_pair, client_iface):
        """Interface-origin walk: the mux PortMapping pushes [N]; the
        unprofiled trunk hop leaves the stack untouched; the far COM rear
        port pops [N] and exits at CH{N}-DEMUX. Channel identity survives
        an unprofiled trunk with NO profile involved, and the path is
        complete when the far client edge is cabled."""
        mux_a, mux_b = mux_pair
        _unprofiled([mux_a.line_ports["tx"].rear_port], [mux_b.line_ports["rx"].rear_port])

        near = client_iface()
        far = client_iface()
        ch3_a = next(ch for ch in mux_a.channels if ch.grid_position == 3)
        ch3_b = next(ch for ch in mux_b.channels if ch.grid_position == 3)
        _unprofiled([near], [ch3_a.mux_front_port])
        _unprofiled([ch3_b.demux_front_port], [far])

        cable_path = Interface.objects.get(pk=near.pk).path
        assert cable_path is not None
        assert cable_path.is_complete is True
        assert cable_path.is_split is False
        assert cable_path.destinations == [far]

        nodes = _flat(cable_path)
        assert _fp(mux_b.device, "CH3-DEMUX") in nodes
        # The strand-space failure mode (exit at CH1) does NOT occur here.
        assert _fp(mux_b.device, "CH1-DEMUX") not in nodes

    def test_native_trace_through_pp_chain_unprofiled(self, mux_pair, client_iface, wdm_site, dt_pp, wdm_roles):
        """Three unprofiled simplex cables through a patch-panel pair
        (RP->FP PortMapping on each panel, positions=1): the channel
        position pushed at the near mux survives every hop and selects
        CH5-DEMUX on the far mux."""
        mux_a, mux_b = mux_pair
        pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "UP-PP-A")
        pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "UP-PP-B")
        _unprofiled([mux_a.line_ports["tx"].rear_port], [_fp(pp_a, "FP-01")], "UP A-patch")
        _unprofiled([_rp(pp_a, "RP-01")], [_rp(pp_b, "RP-01")], "UP trunk")
        _unprofiled([_fp(pp_b, "FP-01")], [mux_b.line_ports["rx"].rear_port], "UP B-patch")

        near = client_iface()
        ch5_a = next(ch for ch in mux_a.channels if ch.grid_position == 5)
        _unprofiled([near], [ch5_a.mux_front_port])

        cable_path = Interface.objects.get(pk=near.pk).path
        assert cable_path is not None
        assert cable_path.is_split is False

        groups = _decompiled(cable_path)
        assert groups[-1] == [_fp(mux_b.device, "CH5-DEMUX")]
        # Dark far client edge: path ends at the demux port, incomplete.
        assert cable_path.is_complete is False

    def test_seeded_walk_aborts_at_far_rear_port(self, mux_pair):
        """The dark-channel seeded walk CANNOT cross an unprofiled hop: the
        in-memory cable_positions seed is only consumed by the profiled
        branch's empty-stack fallback. On the legacy branch the stack stays
        empty, so the far multi-position COM rear port aborts the trace
        (is_split=True) for every seeded position."""
        mux_a, mux_b = mux_pair
        _unprofiled([mux_a.line_ports["tx"].rear_port], [mux_b.line_ports["rx"].rear_port])
        com_tx = mux_a.line_ports["tx"].rear_port

        for position in (1, 3):
            path = trace_segment_from_rear_port(com_tx, position)
            assert path.is_split is True, f"position {position}"
            assert path.is_complete is False
            nodes = _flat(path)
            # The walk records the far COM rear port but never resolves a
            # channel front port on either mux.
            assert mux_b.line_ports["rx"].rear_port in nodes
            assert not any(isinstance(obj, FrontPort) for obj in nodes)


@pytest.mark.django_db(transaction=True)
class TestUnprofiledMultiTermination:
    """Two rear ports per cable end (the duplex builders' shape), unprofiled.

    Without connector rows the legacy branch resolves the far end by
    (cable, cable_end) only, so the walk fans out to BOTH fibres.
    """

    def _duplex_trunk(self, mux_a, mux_b):
        return _unprofiled(
            [mux_a.line_ports["tx"].rear_port, mux_a.line_ports["rx"].rear_port],
            [mux_b.line_ports["rx"].rear_port, mux_b.line_ports["tx"].rear_port],
            "UP duplex trunk",
        )

    def test_fanout_completes_to_both_directions(self, mux_pair, client_iface):
        """Channel position N survives (both far PortMapping lookups happen
        at position N), but the walk cannot tell TX from RX: it continues
        through BOTH far COM rear ports and completes to BOTH far client
        interfaces -- the true RX peer and the wrong-direction TX peer."""
        mux_a, mux_b = mux_pair
        self._duplex_trunk(mux_a, mux_b)

        near = client_iface()
        far_rx = client_iface()
        far_wrong = client_iface()
        ch3_a = next(ch for ch in mux_a.channels if ch.grid_position == 3)
        ch3_b = next(ch for ch in mux_b.channels if ch.grid_position == 3)
        _unprofiled([near], [ch3_a.mux_front_port])
        _unprofiled([ch3_b.demux_front_port], [far_rx])
        _unprofiled([ch3_b.mux_front_port], [far_wrong])

        cable_path = Interface.objects.get(pk=near.pk).path
        assert cable_path is not None
        assert cable_path.is_complete is True
        # Channel identity survived: only grid position 3 ports appear.
        nodes = _flat(cable_path)
        assert _fp(mux_b.device, "CH3-DEMUX") in nodes
        assert _fp(mux_b.device, "CH1-DEMUX") not in nodes
        # ...but direction did not: the wrong-direction peer is a
        # destination alongside the real one.
        assert set(cable_path.destinations) == {far_rx, far_wrong}

    def test_fanout_splits_when_only_rx_is_cabled(self, mux_pair, client_iface):
        """With only the legitimate far DEMUX client cabled, the fan-out
        leaves the wrong-direction CH3-MUX dangling: step 3 marks the path
        split and incomplete, but when the surviving branch later reaches a
        live endpoint the final endpoint check overwrites is_complete back
        to True (cables.py step 8 else-branch). A split path can therefore
        still report itself complete -- consumers must check is_split, not
        just is_complete."""
        mux_a, mux_b = mux_pair
        self._duplex_trunk(mux_a, mux_b)

        near = client_iface()
        far_rx = client_iface()
        ch3_a = next(ch for ch in mux_a.channels if ch.grid_position == 3)
        ch3_b = next(ch for ch in mux_b.channels if ch.grid_position == 3)
        _unprofiled([near], [ch3_a.mux_front_port])
        _unprofiled([ch3_b.demux_front_port], [far_rx])

        cable_path = Interface.objects.get(pk=near.pk).path
        assert cable_path is not None
        assert cable_path.is_split is True
        assert cable_path.is_complete is True
        assert set(cable_path.destinations) == {far_rx}

    def test_duplex_pp_chain_channel_survives_direction_lost(self, mux_pair, client_iface, wdm_site, dt_pp, wdm_roles):
        """Unprofiled mirror of cable_duplex_through_pp_pair (3 duplex
        cables via a PP pair): the walk fans out over both fibres at every
        hop, then pops the surviving [N] at the far COM rear ports and
        lands on BOTH CH{N} ports (DEMUX and MUX). Channel number is
        preserved end to end; direction is unrecoverable."""
        mux_a, mux_b = mux_pair
        pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "UPD-PP-A")
        pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "UPD-PP-B")
        _unprofiled(
            [mux_a.line_ports["tx"].rear_port, mux_a.line_ports["rx"].rear_port],
            [_fp(pp_a, "FP-01"), _fp(pp_a, "FP-02")],
            "UPD A-patch",
        )
        _unprofiled(
            [_rp(pp_a, "RP-01"), _rp(pp_a, "RP-02")],
            [_rp(pp_b, "RP-01"), _rp(pp_b, "RP-02")],
            "UPD trunk",
        )
        _unprofiled(
            [_fp(pp_b, "FP-01"), _fp(pp_b, "FP-02")],
            [mux_b.line_ports["rx"].rear_port, mux_b.line_ports["tx"].rear_port],
            "UPD B-patch",
        )

        near = client_iface()
        ch3_a = next(ch for ch in mux_a.channels if ch.grid_position == 3)
        _unprofiled([near], [ch3_a.mux_front_port])

        cable_path = Interface.objects.get(pk=near.pk).path
        assert cable_path is not None

        groups = _decompiled(cable_path)
        assert set(groups[-1]) == {_fp(mux_b.device, "CH3-DEMUX"), _fp(mux_b.device, "CH3-MUX")}
        assert not any(
            isinstance(obj, FrontPort) and obj.device == mux_b.device and "CH3" not in obj.name
            for obj in _flat(cable_path)
        )

    def test_seeded_walk_aborts_on_multiterm_unprofiled(self, mux_pair):
        """Same abort as the simplex case, reached via the fan-out: the
        seeded rear-port origin crosses to BOTH far COM rear ports with an
        empty stack and the trace aborts split."""
        mux_a, mux_b = mux_pair
        self._duplex_trunk(mux_a, mux_b)

        path = trace_segment_from_rear_port(mux_a.line_ports["tx"].rear_port, 3)
        assert path.is_split is True
        nodes = _flat(path)
        # Fan-out is visible even in the aborted path: both far rear ports.
        assert mux_b.line_ports["rx"].rear_port in nodes
        assert mux_b.line_ports["tx"].rear_port in nodes
        assert not any(isinstance(obj, FrontPort) for obj in nodes)
