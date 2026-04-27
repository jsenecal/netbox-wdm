"""Tests for duplex cabling, multi-TX ROADM tracing, and pass-through topologies."""

import pytest

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.testing import duplex_mux_pair, mux_roadm_mux, sf_mux_pair
from netbox_wdm.trace import rebuild_wavelength_paths_for_node, trace_wavelength_path


@pytest.mark.django_db(transaction=True)
class TestDuplexCabling:
    """Duplex cable_duplex_through_pp_pair creates 3 multi-terminated cables."""

    def test_duplex_topology_creates_three_cables(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        assert len(topo.cables) == 3

    def test_duplex_cables_have_two_terminations_per_side(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        from dcim.models import CableTermination

        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        for cable in topo.cables:
            a_count = CableTermination.objects.filter(cable=cable, cable_end="A").count()
            b_count = CableTermination.objects.filter(cable=cable, cable_end="B").count()
            assert a_count == 2, f"Cable {cable.label} should have 2 A-side terminations"
            assert b_count == 2, f"Cable {cable.label} should have 2 B-side terminations"

    def test_duplex_bidirectional_paths(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        """Both A→B and B→A paths are created for each wavelength."""
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)
        # 8 channels × 2 directions = 16 paths
        assert WdmWavelengthPath.objects.count() == 16

    def test_duplex_paths_are_complete(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)
        for path in WdmWavelengthPath.objects.all():
            assert path.is_complete is True
            assert path.is_active is True

    def test_duplex_path_directions(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        """Each wavelength has both A→B and B→A paths."""
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        node_a = topo.bundles["mux_a"].node
        node_b = topo.bundles["mux_b"].node
        ch = topo.bundles["mux_a"].channels[0]

        # Find paths for first wavelength
        paths = WdmWavelengthPath.objects.filter(grid_position=ch.grid_position)
        assert paths.count() == 2

        directions = set()
        for p in paths:
            entries = list(p.path_channels.order_by("sequence"))
            first_node = entries[0].channel.wdm_node_id
            last_node = entries[-1].channel.wdm_node_id
            directions.add((first_node, last_node))

        assert (node_a.pk, node_b.pk) in directions
        assert (node_b.pk, node_a.pk) in directions


@pytest.mark.django_db(transaction=True)
class TestROADMPassThrough:
    """MUX-A → ROADM → MUX-B pass-through topology with multi-TX tracing."""

    def test_topology_creates_six_cables(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        assert len(topo.cables) == 6  # 3 east + 3 west

    def test_passthrough_creates_three_hop_paths(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        """Pass-through paths have 3 hops: MUX-A → ROADM → MUX-B."""
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        # At least some 3-hop paths should exist
        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]
        assert len(three_hop) > 0, "Should have at least one 3-hop pass-through path"

    def test_passthrough_path_traverses_roadm(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        """Pass-through path visits MUX-A, ROADM, and MUX-B."""
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        node_a = topo.bundles["mux_a"].node
        node_roadm = topo.bundles["roadm"].node
        node_b = topo.bundles["mux_b"].node

        # Find a 3-hop path starting from MUX-A
        for p in WdmWavelengthPath.objects.all():
            entries = list(p.path_channels.order_by("sequence"))
            if len(entries) == 3 and entries[0].channel.wdm_node_id == node_a.pk:
                nodes = [e.channel.wdm_node_id for e in entries]
                assert nodes == [node_a.pk, node_roadm.pk, node_b.pk]
                return

        pytest.fail("No A→ROADM→B path found")

    def test_passthrough_bidirectional(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        """Pass-through paths exist in both directions."""
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        node_a = topo.bundles["mux_a"].node
        node_b = topo.bundles["mux_b"].node

        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]

        a_to_b = [
            p for p in three_hop if list(p.path_channels.order_by("sequence"))[0].channel.wdm_node_id == node_a.pk
        ]
        b_to_a = [
            p for p in three_hop if list(p.path_channels.order_by("sequence"))[0].channel.wdm_node_id == node_b.pk
        ]

        assert len(a_to_b) > 0, "Should have A→ROADM→B paths"
        assert len(b_to_a) > 0, "Should have B→ROADM→A paths"

    def test_passthrough_paths_are_complete(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]
        for p in three_hop:
            assert p.is_complete is True
            assert p.is_active is True


@pytest.mark.django_db(transaction=True)
class TestMultiTXTracing:
    """trace_wavelength_path correctly picks the unvisited TX port on multi-TX nodes."""

    def test_trace_prefers_unvisited_tx_port(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        """From MUX-A, the trace should pass through ROADM to MUX-B (not loop back via EAST-TX)."""
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        ch_a = topo.bundles["mux_a"].channels[0]
        result = trace_wavelength_path(ch_a)

        assert len(result.channels) == 3, f"Expected 3-hop path, got {len(result.channels)}"
        node_names = [ch.wdm_node.device.name for ch in result.channels]
        assert "ROADM" in node_names[1], f"Middle hop should be ROADM, got {node_names}"

    def test_trace_from_far_end_also_passes_through(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        """From MUX-B, the trace should also pass through ROADM to MUX-A."""
        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        ch_b = topo.bundles["mux_b"].channels[0]
        result = trace_wavelength_path(ch_b)

        assert len(result.channels) == 3, f"Expected 3-hop path, got {len(result.channels)}"


@pytest.mark.django_db(transaction=True)
class TestDirectedTraceSegment:
    """_trace_cable_segment with to_node selects the correct direction."""

    def test_trace_segment_reaches_target(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        from netbox_wdm.views import _trace_cable_segment

        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        roadm_node = topo.bundles["roadm"].node
        mux_b_node = topo.bundles["mux_b"].node

        # Trace from ROADM toward MUX-B (should use WEST-TX, not EAST-TX)
        items = _trace_cable_segment(roadm_node, mux_b_node)
        assert len(items) > 0, "Segment should have items"

        # Last port item should be on MUX-B
        port_items = [it for it in items if it.type != "cable"]
        last_device = port_items[-1].device if port_items else None
        assert last_device == mux_b_node.device.name, f"Last device should be MUX-B, got {last_device}"

    def test_trace_segment_other_direction(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        from netbox_wdm.views import _trace_cable_segment

        topo = mux_roadm_mux(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        roadm_node = topo.bundles["roadm"].node
        mux_a_node = topo.bundles["mux_a"].node

        # Trace from ROADM toward MUX-A (should use EAST-TX)
        items = _trace_cable_segment(roadm_node, mux_a_node)
        assert len(items) > 0

        port_items = [it for it in items if it.type != "cable"]
        last_device = port_items[-1].device if port_items else None
        assert last_device == mux_a_node.device.name, f"Last device should be MUX-A, got {last_device}"


@pytest.mark.django_db(transaction=True)
class TestSingleFiberTraceData:
    """Single-fiber (bidi) MUX trace data includes far-end channel port."""

    def test_sf_trace_segment_reaches_far_com(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """Cable segment for SF MUX pair includes far-end COM port."""
        from netbox_wdm.views import _trace_cable_segment

        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        node_a = topo.bundles["mux_a"].node
        node_b = topo.bundles["mux_b"].node

        items = _trace_cable_segment(node_a, node_b)
        port_items = [it for it in items if it.type != "cable"]
        assert len(port_items) >= 2
        assert port_items[0].device == node_a.device.name
        assert port_items[-1].device == node_b.device.name

    def test_sf_path_elements_have_mux_port_no_demux(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """SF MUX PathElements have mux_port but no demux_port (bidi channel)."""

        from netbox_wdm.views import _build_trace_data_for_path

        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        path = WdmWavelengthPath.objects.first()
        td = _build_trace_data_for_path(path)

        for el in td.elements:
            assert el.mux_port is not None, f"SF element on {el.node_name} should have mux_port"
            assert el.demux_port is None, f"SF element on {el.node_name} should have no demux_port"

    def test_sf_trace_data_cable_segment_has_far_end_com(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """The cable segment items include the far-end COM rear port."""
        from netbox_wdm.views import _build_trace_data_for_path

        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        path = WdmWavelengthPath.objects.first()
        td = _build_trace_data_for_path(path)
        assert len(td.cable_segments) >= 1

        seg = td.cable_segments[0]
        port_items = [it for it in seg.items if it.type != "cable"]
        devices = {it.device for it in port_items}
        # Both MUX devices should appear in the cable segment
        assert len(devices) >= 2, f"Expected ports from at least 2 devices, got {devices}"

    def test_sf_highlight_data_includes_far_channel_port(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """For the JS highlight, the far-end mux_port ID must be reachable.

        Since SF has no demux_port, the path set should fall back to
        dst.mux_port. This test verifies that the source mux_port,
        far-end COM, and far-end mux_port are all in the same trace.
        """
        from netbox_wdm.views import _build_trace_data_for_path

        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        for bundle in topo.bundles.values():
            rebuild_wavelength_paths_for_node(bundle.node)

        path = WdmWavelengthPath.objects.first()
        td = _build_trace_data_for_path(path)

        src = td.elements[0]
        dst = td.elements[-1]

        # Collect all port IDs from cable segments
        seg_port_ids = set()
        for seg in td.cable_segments:
            for item in seg.items:
                if item.type != "cable":
                    seg_port_ids.add(item.id)

        # Source mux_port should be known
        assert src.mux_port is not None
        # Far-end mux_port should be known (fallback for missing demux_port)
        assert dst.mux_port is not None
        assert dst.demux_port is None, "SF should have no demux_port"

        # The cable segment should contain both COM ports (first and last)
        # so the JS can build: src.mux_port → COM(A) → ... → COM(B) → dst.mux_port
        port_items = []
        for seg in td.cable_segments:
            port_items.extend([it for it in seg.items if it.type != "cable"])
        first_port = port_items[0]
        last_port = port_items[-1]
        # First port is source COM, last port is far-end COM
        assert first_port.device == src.node_name
        assert last_port.device == dst.node_name
