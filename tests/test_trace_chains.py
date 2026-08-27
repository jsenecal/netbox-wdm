"""Traversal across arbitrary pass-through chains and mid-span carrier circuits.

The walker used to understand exactly one cabling permutation -- a patch
panel entered at its front port and left at a rear-to-rear trunk. Panels
cascaded rear-to-front, and circuit terminations of any shape, ended the
walk early and left the wavelength path undiscovered (issue #49).
"""

import logging

import pytest
from django.conf import settings
from django.test import override_settings

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.testing import (
    cascaded_pp_chain,
    create_patch_panel,
    create_sf_mux,
    midspan_circuit_span,
    simplex_cable,
)
from netbox_wdm.trace import _get_far_end_node, rebuild_wavelength_paths_for_node
from netbox_wdm.views import _trace_cable_segment


def _far_end_of(topo):
    """Walk from MUX-A's line rear port and return the discovered (node, far rear port)."""
    node, _module, far_rp = _get_far_end_node(topo.bundles["mux_a"].line_ports["bidi"].rear_port)
    return node, far_rp


@pytest.mark.django_db
class TestCascadedPanels:
    """Panels cascaded rear-to-front: PP-N.RP patches into PP-N+1.FP."""

    def test_discovers_far_end_node(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = cascaded_pp_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, panels=3)
        node, far_rp = _far_end_of(topo)
        assert node == topo.bundles["mux_b"].node
        assert far_rp == topo.bundles["mux_b"].line_ports["bidi"].rear_port

    def test_traces_wavelength_paths_end_to_end(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = cascaded_pp_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, panels=3)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 8
        path = WdmWavelengthPath.objects.first()
        assert {ch.wdm_node.pk for ch in path.get_channels()} == {
            topo.bundles["mux_a"].node.pk,
            topo.bundles["mux_b"].node.pk,
        }

    def test_rendered_segment_reaches_far_end(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = cascaded_pp_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, panels=3)
        far_rp = topo.bundles["mux_b"].line_ports["bidi"].rear_port
        items = _trace_cable_segment(topo.bundles["mux_a"].node, topo.bundles["mux_b"].node)
        assert any(item.type == "rear_port" and item.id == far_rp.pk for item in items)


@pytest.mark.django_db
class TestMidspanCircuit:
    """A leased carrier circuit joining two halves of the fibre run."""

    def test_discovers_far_end_node_across_circuit(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = midspan_circuit_span(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        node, far_rp = _far_end_of(topo)
        assert node == topo.bundles["mux_b"].node
        assert far_rp == topo.bundles["mux_b"].line_ports["bidi"].rear_port

    def test_traces_wavelength_paths_end_to_end(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = midspan_circuit_span(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 8
        path = WdmWavelengthPath.objects.first()
        assert {ch.wdm_node.pk for ch in path.get_channels()} == {
            topo.bundles["mux_a"].node.pk,
            topo.bundles["mux_b"].node.pk,
        }

    def test_rendered_segment_includes_both_terminations(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """The circuit handoff is visible in the trace diagram, not silently skipped."""
        topo = midspan_circuit_span(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        items = _trace_cable_segment(topo.bundles["mux_a"].node, topo.bundles["mux_b"].node)
        terminations = [item for item in items if item.type == "circuit_termination"]
        assert len(terminations) == 2
        assert {item.label for item in terminations} == {"A", "Z"}
        assert all(item.name == topo.circuit.cid for item in terminations)

    def test_rendered_segment_reaches_far_end(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = midspan_circuit_span(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        far_rp = topo.bundles["mux_b"].line_ports["bidi"].rear_port
        items = _trace_cable_segment(topo.bundles["mux_a"].node, topo.bundles["mux_b"].node)
        assert any(item.type == "rear_port" and item.id == far_rp.pk for item in items)


@pytest.mark.django_db
class TestChainToNowhere:
    """A trunk patched into a panel with nothing beyond it.

    The common shape of a partly built plant: fibre is run and patched,
    but the far-end equipment is not installed yet.
    """

    def test_no_far_end_node_and_no_path(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        from dcim.models import FrontPort

        mux = create_sf_mux(wdm_site, dt_cwdm_sf, wdm_roles["wdm-mux"], "DANGLE-MUX")
        pp = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "DANGLE-PP")
        simplex_cable(
            mux.line_ports["bidi"].rear_port,
            FrontPort.objects.get(device=pp, name="FP-01"),
            label="to nowhere",
        )

        node, _module, far_rp = _get_far_end_node(mux.line_ports["bidi"].rear_port)
        assert node is None
        assert far_rp is None

        rebuild_wavelength_paths_for_node(mux.node)
        assert WdmWavelengthPath.objects.count() == 0

    def test_rendered_segment_shows_the_run_without_a_far_end(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """The diagram still draws the cable that exists, ending at the dark panel."""
        from dcim.models import FrontPort

        mux = create_sf_mux(wdm_site, dt_cwdm_sf, wdm_roles["wdm-mux"], "DANGLE-MUX")
        pp = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "DANGLE-PP")
        simplex_cable(
            mux.line_ports["bidi"].rear_port,
            FrontPort.objects.get(device=pp, name="FP-01"),
            label="to nowhere",
        )

        items = _trace_cable_segment(mux.node)
        assert [item.type for item in items][:3] == ["rear_port", "cable", "front_port"]
        assert not any(item.device == "DANGLE-MUX" for item in items if item.type == "front_port")


@pytest.mark.django_db
class TestMiscabledLoop:
    """A cabling loop must abort the walk, not spin forever.

    The core walker has no visited set, so the plugin refuses to hand it a
    chain that revisits a port.
    """

    def test_loop_aborts_and_logs(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, caplog):
        from dcim.models import FrontPort, RearPort

        topo = cascaded_pp_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, panels=2)
        pp_1, pp_2 = topo.patch_panels
        # Patch PP-2's spare rear port back into PP-1's spare front port, and
        # close the ring by joining the two spare ports on the same panels.
        simplex_cable(
            RearPort.objects.get(device=pp_1, name="RP-02"),
            FrontPort.objects.get(device=pp_2, name="FP-02"),
            label="loop leg 1",
        )
        simplex_cable(
            RearPort.objects.get(device=pp_2, name="RP-02"),
            FrontPort.objects.get(device=pp_1, name="FP-02"),
            label="loop leg 2",
        )

        with caplog.at_level(logging.WARNING, logger="netbox_wdm.core_walk"):
            node, _module, _far_rp = _get_far_end_node(RearPort.objects.get(device=pp_1, name="RP-02"))

        assert node is None
        assert "loop" in caplog.text.lower()


@pytest.mark.django_db
class TestHopCapAcrossChains:
    """max_trace_hops bounds the walk in cable segments."""

    def test_cap_truncates_and_logs(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, caplog):
        topo = cascaded_pp_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, panels=6)
        config = {name: dict(cfg) for name, cfg in settings.PLUGINS_CONFIG.items()}
        config.setdefault("netbox_wdm", {})["max_trace_hops"] = 3

        with override_settings(PLUGINS_CONFIG=config):
            with caplog.at_level(logging.WARNING, logger="netbox_wdm.core_walk"):
                node, _far_rp = _far_end_of(topo)

        assert node is None
        assert "max_trace_hops" in caplog.text
