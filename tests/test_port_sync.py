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


@pytest.mark.django_db(transaction=True)
class TestSignalInvalidation:
    def _setup_synced_node(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Helper: create a node and sync it."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        apply_sync(bundle.node)
        bundle.node.refresh_from_db()
        assert bundle.node.port_sync_valid is True
        return bundle

    def test_portmapping_delete_invalidates(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Deleting a PortMapping sets port_sync_valid to False."""
        bundle = self._setup_synced_node(wdm_site, dt_cwdm_dx, wdm_roles)
        node = bundle.node
        line_port_rp_ids = set(node.line_ports.values_list("rear_port_id", flat=True))
        channel_fp_ids = set()
        for ch in node.channels.all():
            if ch.mux_front_port_id:
                channel_fp_ids.add(ch.mux_front_port_id)
            if ch.demux_front_port_id:
                channel_fp_ids.add(ch.demux_front_port_id)
        pm = PortMapping.objects.filter(
            device=node.device, rear_port_id__in=line_port_rp_ids, front_port_id__in=channel_fp_ids
        ).first()
        pm.delete()
        node.refresh_from_db()
        assert node.port_sync_valid is False

    def test_portmapping_create_invalidates(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Creating an extra PortMapping sets port_sync_valid to False."""
        bundle = self._setup_synced_node(wdm_site, dt_cwdm_dx, wdm_roles)
        node = bundle.node
        first_lp = node.line_ports.select_related("rear_port").first()
        # Use a demux front port (RX side) with the TX rear port to create a rogue mapping.
        # front_port_position=999 avoids the unique constraint on (front_port, front_port_position).
        # rear_port_position=999 avoids the unique constraint on (rear_port, rear_port_position).
        PortMapping.objects.create(
            device=node.device,
            front_port_id=bundle.channels[0].mux_front_port_id,
            rear_port=first_lp.rear_port,
            front_port_position=999,
            rear_port_position=999,
        )
        node.refresh_from_db()
        assert node.port_sync_valid is False


from django.test import RequestFactory
from rest_framework.test import force_authenticate
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestSyncPortsAPI:
    def _get_view(self):
        from netbox_wdm.api.views import WdmNodeViewSet
        return WdmNodeViewSet.as_view({"post": "sync_ports"})

    def _make_request(self, node, query_params=None):
        factory = RequestFactory()
        url = f"/api/plugins/wdm/wdm-nodes/{node.pk}/sync-ports/"
        if query_params:
            url += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())
        request = factory.post(url)
        user = User.objects.create_superuser("testadmin", "admin@test.com", "testpass")
        force_authenticate(request, user=user)
        view = self._get_view()
        return view(request, pk=node.pk)

    def test_dry_run_default(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Default request is dry run — no changes applied."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        # Delete mappings to create drift
        PortMapping.objects.filter(device=bundle.node.device).delete()
        response = self._make_request(bundle.node)
        assert response.status_code == 200
        assert response.data["dry_run"] is True
        # Mappings should NOT have been recreated
        assert not check_port_sync(bundle.node)

    def test_dry_run_false_applies(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """dry_run=false actually applies changes."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        PortMapping.objects.filter(device=bundle.node.device).delete()
        response = self._make_request(bundle.node, {"dry_run": "false"})
        assert response.status_code == 200
        assert response.data["dry_run"] is False
        assert response.data["changes"]["port_mappings"]["create"] > 0
        assert check_port_sync(bundle.node)

    def test_response_includes_warnings(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Response includes warnings section."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        response = self._make_request(bundle.node)
        assert "warnings" in response.data
        assert "cables_affected" in response.data["warnings"]
        assert "wavelength_services" in response.data["warnings"]


from django.core.management import call_command
from io import StringIO


@pytest.mark.django_db
class TestSyncPortsCommand:
    def test_sync_command_applies(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Command applies sync and prints report."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        PortMapping.objects.filter(device=bundle.node.device).delete()
        out = StringIO()
        call_command("wdm_sync_ports", str(bundle.node.pk), stdout=out)
        output = out.getvalue()
        assert "Port mappings created" in output
        assert check_port_sync(bundle.node)

    def test_sync_command_dry_run(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Command with --dry-run prints report but doesn't apply."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        PortMapping.objects.filter(device=bundle.node.device).delete()
        out = StringIO()
        call_command("wdm_sync_ports", str(bundle.node.pk), dry_run=True, stdout=out)
        output = out.getvalue()
        assert "DRY RUN" in output
        assert not check_port_sync(bundle.node)

    def test_sync_command_invalid_pk(self):
        """Command with invalid pk raises CommandError."""
        from django.core.management.base import CommandError

        out = StringIO()
        with pytest.raises(CommandError):
            call_command("wdm_sync_ports", "99999", stdout=out)


@pytest.mark.django_db
class TestRehashPortsCommand:
    def test_rehash_computes_hashes(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Command computes hashes for all nodes."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        # Ensure hash is empty (default)
        from netbox_wdm.models import WdmNode

        WdmNode.objects.filter(pk=bundle.node.pk).update(expected_port_hash="")
        out = StringIO()
        call_command("wdm_rehash_ports", stdout=out)
        bundle.node.refresh_from_db()
        assert bundle.node.expected_port_hash != ""
        assert bundle.node.port_sync_valid is True

    def test_rehash_missing_only(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """--missing-only only processes nodes with empty hashes."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        # Set a non-empty hash so --missing-only skips it
        from netbox_wdm.models import WdmNode

        WdmNode.objects.filter(pk=bundle.node.pk).update(expected_port_hash="fakehash")
        out = StringIO()
        call_command("wdm_rehash_ports", missing_only=True, stdout=out)
        output = out.getvalue()
        assert "No nodes to process" in output
        bundle.node.refresh_from_db()
        assert bundle.node.expected_port_hash == "fakehash"

    def test_rehash_detects_out_of_sync(self, wdm_site, dt_cwdm_dx, wdm_roles):
        """Command reports nodes that are out of sync."""
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MUX-A")
        from netbox_wdm.models import WdmNode

        WdmNode.objects.filter(pk=bundle.node.pk).update(expected_port_hash="")
        PortMapping.objects.filter(device=bundle.node.device).delete()
        out = StringIO()
        call_command("wdm_rehash_ports", stdout=out)
        output = out.getvalue()
        assert "out of sync" in output
        bundle.node.refresh_from_db()
        assert bundle.node.port_sync_valid is False
