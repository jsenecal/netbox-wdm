"""Tests for the port sync detection and repair system."""

import pytest
from netbox_wdm.testing import create_cwdm_mux_dx_type, create_device_roles, create_duplex_mux, create_manufacturer, create_site


@pytest.mark.django_db
class TestPortSyncFields:
    def test_wdm_node_has_port_sync_fields(self, wdm_site, dt_cwdm_dx, wdm_roles):
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        assert hasattr(node, "expected_port_hash")
        assert hasattr(node, "port_sync_valid")
        assert node.port_sync_valid is True
        assert node.expected_port_hash == ""
