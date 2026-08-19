"""Regression tests for the configurable trace hop cap (issue #43).

Both traversal engines used to hard-code a 20-hop cap, so a legitimate
chain longer than that silently came back incomplete. The cap is now the
max_trace_hops plugin setting, and hitting it logs a warning.
"""

import logging

import pytest
from django.conf import settings
from django.test import override_settings

from netbox_wdm.testing import sf_mux_long_chain
from netbox_wdm.trace import _get_far_end_node
from netbox_wdm.views import _trace_cable_segment


def _plugins_config(max_trace_hops: int) -> dict:
    """Copy of settings.PLUGINS_CONFIG with max_trace_hops set for netbox_wdm."""
    config = {name: dict(cfg) for name, cfg in settings.PLUGINS_CONFIG.items()}
    config.setdefault("netbox_wdm", {})["max_trace_hops"] = max_trace_hops
    return config


@pytest.mark.django_db
class TestDiscoveryHopCap:
    """Hop cap in trace._get_far_end_node (path discovery engine)."""

    def test_long_chain_resolves_with_raised_cap(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """A 21-hop chain resolves once max_trace_hops is raised above 20 (issue #43)."""
        topo = sf_mux_long_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, passthrough_units=20)
        start_rp = topo.bundles["mux_a"].line_ports["bidi"].rear_port
        with override_settings(PLUGINS_CONFIG=_plugins_config(50)):
            node, module, far_rp = _get_far_end_node(start_rp)
        assert node == topo.bundles["mux_b"].node
        assert module is None
        assert far_rp == topo.bundles["mux_b"].line_ports["bidi"].rear_port

    def test_cap_hit_logs_warning(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, caplog):
        """Hitting the default 20-hop cap truncates discovery and logs a warning (issue #43)."""
        topo = sf_mux_long_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, passthrough_units=20)
        start_rp = topo.bundles["mux_a"].line_ports["bidi"].rear_port
        with caplog.at_level(logging.WARNING, logger="netbox_wdm.trace"):
            node, module, far_rp = _get_far_end_node(start_rp)
        assert node is None
        assert "max_trace_hops" in caplog.text


@pytest.mark.django_db
class TestCableSegmentHopCap:
    """Hop cap in views._trace_cable_segment (trace rendering engine)."""

    def test_long_chain_traces_with_raised_cap(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        """A chain needing more than 20 walk iterations completes with a raised cap (issue #43)."""
        topo = sf_mux_long_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, passthrough_units=10)
        far_rp = topo.bundles["mux_b"].line_ports["bidi"].rear_port
        with override_settings(PLUGINS_CONFIG=_plugins_config(50)):
            items = _trace_cable_segment(topo.bundles["mux_a"].node, topo.bundles["mux_b"].node)
        assert any(item.type == "rear_port" and item.id == far_rp.pk for item in items)

    def test_cap_hit_logs_warning(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, caplog):
        """Hitting the default cap truncates the rendered segment and logs a warning (issue #43)."""
        topo = sf_mux_long_chain(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles, passthrough_units=10)
        far_rp = topo.bundles["mux_b"].line_ports["bidi"].rear_port
        with caplog.at_level(logging.WARNING, logger="netbox_wdm.trace"):
            items = _trace_cable_segment(topo.bundles["mux_a"].node, topo.bundles["mux_b"].node)
        assert not any(item.type == "rear_port" and item.id == far_rp.pk for item in items)
        assert "max_trace_hops" in caplog.text
