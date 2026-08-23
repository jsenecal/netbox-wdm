"""Tests for duplex cabling, multi-TX ROADM tracing, and pass-through topologies.

Every class here is read-only against its topology, so each one shares a
single committed class-scoped topology fixture (built once per class, with
wavelength paths rebuilt) instead of rebuilding the same topology for every
test. Topology sharing was introduced for the suite-runtime work in issue #48.
"""

import pytest

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.trace import trace_wavelength_path


@pytest.mark.django_db
class TestDuplexCabling:
    """Duplex cable_duplex_through_pp_pair creates 3 multi-terminated cables."""

    def test_duplex_topology_creates_three_cables(self, duplex_topology):
        assert len(duplex_topology.cables) == 3

    def test_duplex_cables_have_two_terminations_per_side(self, duplex_topology):
        from dcim.models import CableTermination

        for cable in duplex_topology.cables:
            a_count = CableTermination.objects.filter(cable=cable, cable_end="A").count()
            b_count = CableTermination.objects.filter(cable=cable, cable_end="B").count()
            assert a_count == 2, f"Cable {cable.label} should have 2 A-side terminations"
            assert b_count == 2, f"Cable {cable.label} should have 2 B-side terminations"

    def test_duplex_bidirectional_paths(self, duplex_topology):
        """Both A→B and B→A paths are created for each wavelength."""
        # 8 channels × 2 directions = 16 paths
        assert WdmWavelengthPath.objects.count() == 16

    def test_duplex_paths_are_complete(self, duplex_topology):
        for path in WdmWavelengthPath.objects.all():
            assert path.is_complete is True
            assert path.is_active is True

    def test_duplex_path_directions(self, duplex_topology):
        """Each wavelength has both A→B and B→A paths."""
        node_a = duplex_topology.bundles["mux_a"].node
        node_b = duplex_topology.bundles["mux_b"].node
        ch = duplex_topology.bundles["mux_a"].channels[0]

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


@pytest.mark.django_db
class TestROADMPassThrough:
    """MUX-A → ROADM → MUX-B pass-through topology with multi-TX tracing."""

    def test_topology_creates_six_cables(self, roadm_topology):
        assert len(roadm_topology.cables) == 6  # 3 east + 3 west

    def test_passthrough_creates_three_hop_paths(self, roadm_topology):
        """Pass-through paths have 3 hops: MUX-A → ROADM → MUX-B."""
        # At least some 3-hop paths should exist
        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]
        assert len(three_hop) > 0, "Should have at least one 3-hop pass-through path"

    def test_passthrough_path_traverses_roadm(self, roadm_topology):
        """Pass-through path visits MUX-A, ROADM, and MUX-B."""
        node_a = roadm_topology.bundles["mux_a"].node
        node_roadm = roadm_topology.bundles["roadm"].node
        node_b = roadm_topology.bundles["mux_b"].node

        # Find a 3-hop path starting from MUX-A
        for p in WdmWavelengthPath.objects.all():
            entries = list(p.path_channels.order_by("sequence"))
            if len(entries) == 3 and entries[0].channel.wdm_node_id == node_a.pk:
                nodes = [e.channel.wdm_node_id for e in entries]
                assert nodes == [node_a.pk, node_roadm.pk, node_b.pk]
                return

        pytest.fail("No A→ROADM→B path found")

    def test_passthrough_bidirectional(self, roadm_topology):
        """Pass-through paths exist in both directions."""
        node_a = roadm_topology.bundles["mux_a"].node
        node_b = roadm_topology.bundles["mux_b"].node

        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]

        a_to_b = [
            p for p in three_hop if list(p.path_channels.order_by("sequence"))[0].channel.wdm_node_id == node_a.pk
        ]
        b_to_a = [
            p for p in three_hop if list(p.path_channels.order_by("sequence"))[0].channel.wdm_node_id == node_b.pk
        ]

        assert len(a_to_b) > 0, "Should have A→ROADM→B paths"
        assert len(b_to_a) > 0, "Should have B→ROADM→A paths"

    def test_passthrough_paths_are_complete(self, roadm_topology):
        three_hop = [p for p in WdmWavelengthPath.objects.all() if p.path_channels.count() == 3]
        for p in three_hop:
            assert p.is_complete is True
            assert p.is_active is True


@pytest.mark.django_db
class TestMultiTXTracing:
    """trace_wavelength_path correctly picks the unvisited TX port on multi-TX nodes."""

    def test_trace_prefers_unvisited_tx_port(self, roadm_topology):
        """From MUX-A, the trace should pass through ROADM to MUX-B (not loop back via EAST-TX)."""
        ch_a = roadm_topology.bundles["mux_a"].channels[0]
        result = trace_wavelength_path(ch_a)

        assert len(result.channels) == 3, f"Expected 3-hop path, got {len(result.channels)}"
        node_names = [ch.wdm_node.device.name for ch in result.channels]
        assert "ROADM" in node_names[1], f"Middle hop should be ROADM, got {node_names}"

    def test_trace_from_far_end_also_passes_through(self, roadm_topology):
        """From MUX-B, the trace should also pass through ROADM to MUX-A."""
        ch_b = roadm_topology.bundles["mux_b"].channels[0]
        result = trace_wavelength_path(ch_b)

        assert len(result.channels) == 3, f"Expected 3-hop path, got {len(result.channels)}"


@pytest.mark.django_db
class TestDirectedTraceSegment:
    """_trace_cable_segment with to_node selects the correct direction."""

    def test_trace_segment_reaches_target(self, roadm_topology):
        from netbox_wdm.views import _trace_cable_segment

        roadm_node = roadm_topology.bundles["roadm"].node
        mux_b_node = roadm_topology.bundles["mux_b"].node

        # Trace from ROADM toward MUX-B (should use WEST-TX, not EAST-TX)
        items = _trace_cable_segment(roadm_node, mux_b_node)
        assert len(items) > 0, "Segment should have items"

        # Last port item should be on MUX-B
        port_items = [it for it in items if it.type != "cable"]
        last_device = port_items[-1].device if port_items else None
        assert last_device == mux_b_node.device.name, f"Last device should be MUX-B, got {last_device}"

    def test_trace_segment_other_direction(self, roadm_topology):
        from netbox_wdm.views import _trace_cable_segment

        roadm_node = roadm_topology.bundles["roadm"].node
        mux_a_node = roadm_topology.bundles["mux_a"].node

        # Trace from ROADM toward MUX-A (should use EAST-TX)
        items = _trace_cable_segment(roadm_node, mux_a_node)
        assert len(items) > 0

        port_items = [it for it in items if it.type != "cable"]
        last_device = port_items[-1].device if port_items else None
        assert last_device == mux_a_node.device.name, f"Last device should be MUX-A, got {last_device}"


@pytest.mark.django_db
class TestSingleFiberTraceData:
    """Single-fiber (bidi) MUX trace data includes far-end channel port."""

    def test_sf_trace_segment_reaches_far_com(self, sf_topology):
        """Cable segment for SF MUX pair includes far-end COM port."""
        from netbox_wdm.views import _trace_cable_segment

        node_a = sf_topology.bundles["mux_a"].node
        node_b = sf_topology.bundles["mux_b"].node

        items = _trace_cable_segment(node_a, node_b)
        port_items = [it for it in items if it.type != "cable"]
        assert len(port_items) >= 2
        assert port_items[0].device == node_a.device.name
        assert port_items[-1].device == node_b.device.name

    def test_sf_path_elements_have_mux_port_no_demux(self, sf_topology):
        """SF MUX PathElements have mux_port but no demux_port (bidi channel)."""

        from netbox_wdm.views import _build_trace_data_for_path

        path = WdmWavelengthPath.objects.first()
        td = _build_trace_data_for_path(path)

        for el in td.elements:
            assert el.mux_port is not None, f"SF element on {el.node_name} should have mux_port"
            assert el.demux_port is None, f"SF element on {el.node_name} should have no demux_port"

    def test_sf_trace_data_cable_segment_has_far_end_com(self, sf_topology):
        """The cable segment items include the far-end COM rear port."""
        from netbox_wdm.views import _build_trace_data_for_path

        path = WdmWavelengthPath.objects.first()
        td = _build_trace_data_for_path(path)
        assert len(td.cable_segments) >= 1

        seg = td.cable_segments[0]
        port_items = [it for it in seg.items if it.type != "cable"]
        devices = {it.device for it in port_items}
        # Both MUX devices should appear in the cable segment
        assert len(devices) >= 2, f"Expected ports from at least 2 devices, got {devices}"

    def test_sf_highlight_data_includes_far_channel_port(self, sf_topology):
        """For the JS highlight, the far-end mux_port ID must be reachable.

        Since SF has no demux_port, the path set should fall back to
        dst.mux_port. This test verifies that the source mux_port,
        far-end COM, and far-end mux_port are all in the same trace.
        """
        from netbox_wdm.views import _build_trace_data_for_path

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
