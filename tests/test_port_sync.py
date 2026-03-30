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


from dcim.models import PortMapping
from netbox_wdm.port_sync import compute_expected_port_hash, compute_actual_port_hash


@pytest.mark.django_db
class TestHashComputation:
    def test_expected_hash_deterministic(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Same node state produces the same hash."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        h1 = compute_expected_port_hash(bundle.node)
        h2 = compute_expected_port_hash(bundle.node)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_expected_hash_nonempty_with_channels(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """A node with channels and line ports produces a non-empty hash."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        h = compute_expected_port_hash(bundle.node)
        assert h != ""

    def test_actual_hash_differs_without_port_mappings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """When PortMappings are removed, the actual hash differs from expected."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        # Delete all auto-created PortMappings to simulate a drift scenario
        PortMapping.objects.filter(device=node.device).delete()
        expected = compute_expected_port_hash(node)
        actual = compute_actual_port_hash(node)
        assert expected != actual

    def test_hashes_match_after_port_mappings_created(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """When correct PortMappings exist, expected and actual hashes match.

        NetBox auto-creates PortMappings from PortTemplateMappings when a device is
        instantiated. The expected hash is computed from WdmChannel + WdmLinePort data;
        the actual hash is computed from the PortMappings that exist on the device.
        They should match when the WdmNode correctly reflects the device type's port layout.
        """
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        expected = compute_expected_port_hash(node)
        actual = compute_actual_port_hash(node)
        assert expected == actual
