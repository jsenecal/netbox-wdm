"""Tests for profile-aware cable strand pairing (regression tests for issue #39).

The tracer used to pair A-side termination N with B-side termination N by pk
order, which silently follows the wrong strand whenever CableTermination pk
order diverges from strand order (e.g. after a strand re-termination).
NetBox 4.6+ cable profiles persist the strand pairing on each
CableTermination (connector/positions), which is authoritative.

The read-only classes share committed class-scoped topology fixtures instead
of rebuilding a topology per test (suite-runtime work in issue #48); the
pk-shuffling class mutates its topology, so it stays function-scoped.
"""

import pytest
from dcim.choices import CableProfileChoices
from dcim.models import CableTermination

from netbox_wdm.testing import duplex_mux_pair
from netbox_wdm.trace import trace_wavelength_path


def _shuffle_strand_pks(cable, cable_end="B", connector=1):
    """Recreate one CableTermination so pk order no longer matches strand order.

    Deleting and re-adding the row gives it the highest pk on its cable end
    while its connector/positions (the authoritative strand identity) are
    preserved. Index pairing by pk then crosses the strands; profile-aware
    pairing is unaffected.
    """
    ct = CableTermination.objects.get(cable=cable, cable_end=cable_end, connector=connector)
    replacement = CableTermination(
        cable=ct.cable,
        cable_end=ct.cable_end,
        connector=ct.connector,
        positions=ct.positions,
        termination=ct.termination,
    )
    ct.delete()
    replacement.save()


@pytest.mark.django_db
class TestBuilderCableProfiles:
    """The testing builders assign cable profiles so strand pairing is explicit."""

    def test_duplex_builder_sets_trunk_2c1p_profile(self, duplex_topology):
        for cable in duplex_topology.cables:
            assert cable.profile == CableProfileChoices.TRUNK_2C1P, f"Cable {cable.label} missing duplex profile"

    def test_duplex_builder_populates_connectors(self, duplex_topology):
        for cable in duplex_topology.cables:
            connectors = sorted(
                CableTermination.objects.filter(cable=cable, cable_end="A").values_list("connector", flat=True)
            )
            assert connectors == [1, 2], f"Cable {cable.label} A-side connectors: {connectors}"

    def test_simplex_builder_sets_single_1c1p_profile(self, sf_topology):
        for cable in sf_topology.cables:
            assert cable.profile == CableProfileChoices.SINGLE_1C1P, f"Cable {cable.label} missing simplex profile"


@pytest.mark.django_db(transaction=True)
class TestProfileAwarePairing:
    """Strand pairing follows profile connectors, not CableTermination pk order.

    Regression tests for issue #39: pk-order index pairing follows the wrong
    strand when termination rows are recreated out of creation order.

    These tests mutate their topology (recreating strand terminations), so
    they build a fresh function-scoped topology instead of sharing the
    committed class-scoped one.
    """

    def _profiled_duplex_topology(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        # Assign profiles explicitly so the test does not depend on builder defaults.
        for cable in topo.cables:
            if cable.profile != CableProfileChoices.TRUNK_2C1P:
                cable.profile = CableProfileChoices.TRUNK_2C1P
                cable.save()
        return topo

    def test_trace_follows_connectors_after_pk_reorder(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        """Recreating a trunk strand termination must not cross TX/RX strands."""
        topo = self._profiled_duplex_topology(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        trunk = topo.cables[1]
        _shuffle_strand_pks(trunk)

        mux_a = topo.bundles["mux_a"]
        mux_b = topo.bundles["mux_b"]
        result = trace_wavelength_path(mux_a.channels[0])

        assert {ch.wdm_node_id for ch in result.channels} == {mux_a.node.pk, mux_b.node.pk}
        assert result.is_valid is True, "pk-order pairing crossed the strands (TX landed on far-end TX)"
        assert result.is_complete is True

    def test_views_segment_follows_connectors_after_pk_reorder(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        """The visualization cable walk must land on the far-end RX strand."""
        from netbox_wdm.views import _trace_cable_segment

        topo = self._profiled_duplex_topology(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        trunk = topo.cables[1]
        _shuffle_strand_pks(trunk)

        mux_a = topo.bundles["mux_a"]
        mux_b = topo.bundles["mux_b"]
        items = _trace_cable_segment(mux_a.node, mux_b.node)

        port_items = [it for it in items if it.type != "cable"]
        last_port = port_items[-1]
        assert last_port.device == mux_b.node.device.name
        expected_rx = mux_b.line_ports["rx"].rear_port
        assert last_port.id == expected_rx.pk, (
            f"Segment ended on {last_port.name}, expected RX strand {expected_rx.name}"
        )


@pytest.mark.django_db
class TestUnprofiledDuplex:
    """Unprofiled legacy cables carry no strand identity; role resolves direction.

    Core follows every fibre of an unprofiled multi-terminated cable at
    once, so both far line ports come back. The trace picks the one whose
    WdmLinePort role complements the origin's, rather than guessing the
    strand from termination row order as it once did (issue #49).
    """

    def test_unprofiled_duplex_still_traces(self, unprofiled_duplex_topology):
        mux_a = unprofiled_duplex_topology.bundles["mux_a"]
        mux_b = unprofiled_duplex_topology.bundles["mux_b"]

        result = trace_wavelength_path(mux_a.channels[0])
        assert {ch.wdm_node_id for ch in result.channels} == {mux_a.node.pk, mux_b.node.pk}
        assert result.is_valid is True

    def test_unprofiled_duplex_lands_on_far_rx_strand(self, unprofiled_duplex_topology):
        """A TX origin resolves to the far RX line port, not the far TX beside it."""
        from netbox_wdm.trace import _get_far_end_node

        mux_a = unprofiled_duplex_topology.bundles["mux_a"]
        mux_b = unprofiled_duplex_topology.bundles["mux_b"]

        node, _module, far_rp = _get_far_end_node(mux_a.line_ports["tx"].rear_port)

        assert node == mux_b.node
        assert far_rp == mux_b.line_ports["rx"].rear_port

    def test_unprofiled_duplex_keeps_both_directions(self, unprofiled_duplex_topology):
        """Losing strand identity must not collapse the two directional paths into one.

        The fixture rebuilds paths on both nodes when it commits the topology.
        """
        from netbox_wdm.models import WdmWavelengthPath

        assert WdmWavelengthPath.objects.count() == 16  # 8 channels x 2 directions
