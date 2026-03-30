"""Tests for the port sync detection and repair system."""

import pytest
from netbox_wdm.testing import create_cwdm_mux_dx_type, create_device_roles, create_duplex_mux, create_manufacturer, create_site
from netbox_wdm.port_sync import compute_sync_diff, apply_sync, check_port_sync


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


@pytest.mark.django_db
class TestSyncDiff:
    def test_diff_clean_when_in_sync(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """No changes reported when everything is in sync (auto-created PortMappings)."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        diff = compute_sync_diff(bundle.node)
        assert diff["changes"]["port_mappings"]["create"] == 0
        assert diff["changes"]["port_mappings"]["delete"] == 0

    def test_diff_detects_missing_port_mappings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Diff reports port_mappings to create when they are deleted."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        # Delete all PortMappings to simulate drift
        PortMapping.objects.filter(device=bundle.node.device).delete()
        diff = compute_sync_diff(bundle.node)
        assert diff["changes"]["port_mappings"]["create"] > 0
        assert diff["changes"]["port_mappings"]["delete"] == 0

    def test_diff_detects_extra_port_mappings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Diff reports port_mappings to delete when extras exist (wrong rear_port_position)."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        first_ch = node.channels.first()
        # Corrupt the rear_port_position on the first channel's mux mapping so it becomes
        # an "actual" entry that doesn't match the expected grid_position.
        PortMapping.objects.filter(
            device=node.device,
            front_port_id=first_ch.mux_front_port_id,
        ).update(rear_port_position=999)
        diff = compute_sync_diff(node)
        assert diff["changes"]["port_mappings"]["delete"] > 0


@pytest.mark.django_db
class TestApplySync:
    def test_sync_restores_deleted_port_mappings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Sync recreates PortMappings after they are deleted."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        # Delete all mappings
        PortMapping.objects.filter(device=node.device).delete()
        assert not check_port_sync(node)
        result = apply_sync(node)
        assert result["changes"]["port_mappings"]["create"] > 0
        assert check_port_sync(node)

    def test_sync_removes_extra_port_mappings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Sync removes PortMappings that shouldn't exist (wrong rear_port_position)."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        node = bundle.node
        # Corrupt the rear_port_position so the actual mapping no longer matches expected.
        PortMapping.objects.filter(
            device=node.device,
            front_port_id=bundle.channels[0].mux_front_port_id,
        ).update(rear_port_position=999)
        result = apply_sync(node)
        assert result["changes"]["port_mappings"]["delete"] > 0
        assert check_port_sync(node)

    def test_sync_sets_port_sync_valid(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """After sync, node.port_sync_valid is True."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        PortMapping.objects.filter(device=bundle.node.device).delete()
        apply_sync(bundle.node)
        bundle.node.refresh_from_db()
        assert bundle.node.port_sync_valid is True

    def test_sync_idempotent(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Running sync twice produces no changes on second run."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        apply_sync(bundle.node)
        result = apply_sync(bundle.node)
        assert result["changes"]["port_mappings"]["create"] == 0
        assert result["changes"]["port_mappings"]["delete"] == 0
