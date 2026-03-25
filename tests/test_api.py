"""Tests for WDM REST API endpoints."""

import pytest
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from rest_framework import status
from rest_framework.test import APIClient

from netbox_wdm.choices import (
    WdmChannelStatusChoices,
    WdmCircuitStatusChoices,
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmNodeTypeChoices,
)
from netbox_wdm.models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmCircuitPath,
    WdmLinePort,
    WdmNode,
    WdmProfile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """Authenticated DRF test client with superuser-level access."""
    from users.models import User

    user = User.objects.create_superuser(username="test_api_user", password="password")
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def site():
    return Site.objects.create(name="API Test Site", slug="api-test-site")


@pytest.fixture
def manufacturer():
    return Manufacturer.objects.create(name="API Manufacturer", slug="api-manufacturer")


@pytest.fixture
def device_role():
    return DeviceRole.objects.create(name="API WDM Role", slug="api-wdm-role")


@pytest.fixture
def device_type(manufacturer):
    return DeviceType.objects.create(
        manufacturer=manufacturer,
        model="API MUX 44ch",
        slug="api-mux-44ch",
    )


@pytest.fixture
def device(site, device_type, device_role):
    return Device.objects.create(
        name="API-MUX-A",
        site=site,
        device_type=device_type,
        role=device_role,
    )


@pytest.fixture
def profile(device_type):
    return WdmProfile.objects.create(
        device_type=device_type,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )


@pytest.fixture
def wdm_node(device):
    return WdmNode.objects.create(
        device=device,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )


@pytest.fixture
def channel(wdm_node):
    return WdmChannel.objects.create(
        wdm_node=wdm_node,
        grid_position=1,
        wavelength_nm="1560.61",
        label="C21",
    )


@pytest.fixture
def circuit():
    return WdmCircuit.objects.create(
        name="Test Circuit",
        status=WdmCircuitStatusChoices.PLANNED,
        wavelength_nm="1560.61",
    )


# ---------------------------------------------------------------------------
# WdmProfile API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmProfileAPI:
    base_url = "/api/plugins/wdm/wdm-profiles/"

    def test_list(self, api_client, profile):
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, profile):
        response = api_client.get(f"{self.base_url}{profile.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == profile.pk
        assert response.data["node_type"] == WdmNodeTypeChoices.TERMINAL_MUX
        assert response.data["grid"] == WdmGridChoices.DWDM_100GHZ

    def test_create(self, api_client, manufacturer):
        new_dt = DeviceType.objects.create(
            manufacturer=manufacturer,
            model="New MUX",
            slug="new-mux",
        )
        response = api_client.post(
            self.base_url,
            {
                "device_type": new_dt.pk,
                "node_type": WdmNodeTypeChoices.ROADM,
                "grid": WdmGridChoices.DWDM_50GHZ,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["node_type"] == WdmNodeTypeChoices.ROADM

    def test_update(self, api_client, profile):
        response = api_client.patch(
            f"{self.base_url}{profile.pk}/",
            {"description": "Updated description"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description"] == "Updated description"

    def test_delete(self, api_client, device_type, manufacturer):
        other_dt = DeviceType.objects.create(
            manufacturer=manufacturer,
            model="Delete Target",
            slug="delete-target",
        )
        target = WdmProfile.objects.create(
            device_type=other_dt,
            node_type=WdmNodeTypeChoices.AMPLIFIER,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        response = api_client.delete(f"{self.base_url}{target.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not WdmProfile.objects.filter(pk=target.pk).exists()


# ---------------------------------------------------------------------------
# WdmChannelPlan API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmChannelPlanAPI:
    base_url = "/api/plugins/wdm/wdm-channel-plans/"

    def test_list(self, api_client, profile):
        WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm="1560.61", label="C21")
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, profile):
        cp = WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm="1560.61", label="C21")
        response = api_client.get(f"{self.base_url}{cp.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["label"] == "C21"

    def test_create(self, api_client, profile):
        response = api_client.post(
            self.base_url,
            {
                "profile": profile.pk,
                "grid_position": 5,
                "wavelength_nm": "1557.36",
                "label": "C25",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["label"] == "C25"

    def test_update(self, api_client, profile):
        cp = WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm="1560.61", label="C21")
        response = api_client.patch(
            f"{self.base_url}{cp.pk}/",
            {"label": "C21-updated"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["label"] == "C21-updated"

    def test_delete(self, api_client, profile):
        cp = WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm="1560.61", label="C21")
        response = api_client.delete(f"{self.base_url}{cp.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ---------------------------------------------------------------------------
# WdmNode API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmNodeAPI:
    base_url = "/api/plugins/wdm/wdm-nodes/"

    def test_list(self, api_client, wdm_node):
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, wdm_node):
        response = api_client.get(f"{self.base_url}{wdm_node.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == wdm_node.pk

    def test_create(self, api_client, site, device_type, device_role):
        new_device = Device.objects.create(
            name="API-MUX-B",
            site=site,
            device_type=device_type,
            role=device_role,
        )
        response = api_client.post(
            self.base_url,
            {
                "device": new_device.pk,
                "node_type": WdmNodeTypeChoices.TERMINAL_MUX,
                "grid": WdmGridChoices.DWDM_100GHZ,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_update(self, api_client, wdm_node):
        response = api_client.patch(
            f"{self.base_url}{wdm_node.pk}/",
            {"description": "Node description updated"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description"] == "Node description updated"

    def test_delete(self, api_client, site, device_type, device_role):
        device = Device.objects.create(
            name="API-MUX-DEL",
            site=site,
            device_type=device_type,
            role=device_role,
        )
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.AMPLIFIER,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        response = api_client.delete(f"{self.base_url}{node.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ---------------------------------------------------------------------------
# apply-mapping endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApplyMappingAPI:
    def _url(self, node_pk):
        return f"/api/plugins/wdm/wdm-nodes/{node_pk}/apply-mapping/"

    def test_valid_mapping(self, api_client, wdm_node):
        ch = WdmChannel.objects.create(
            wdm_node=wdm_node,
            grid_position=1,
            wavelength_nm="1560.61",
            label="C21",
        )
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {str(ch.pk): None}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "added" in response.data
        assert "removed" in response.data
        assert "changed" in response.data

    def test_reject_lit_channel_remap(self, api_client, wdm_node):
        ch = WdmChannel.objects.create(
            wdm_node=wdm_node,
            grid_position=1,
            wavelength_nm="1560.61",
            label="C21",
            status=WdmChannelStatusChoices.ACTIVE,
        )
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {str(ch.pk): 999}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
        assert len(response.data["errors"]) >= 1

    def test_reject_reserved_channel_remap(self, api_client, wdm_node):
        ch = WdmChannel.objects.create(
            wdm_node=wdm_node,
            grid_position=1,
            wavelength_nm="1560.61",
            label="C21",
            status=WdmChannelStatusChoices.RESERVED,
        )
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {str(ch.pk): 999}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data

    def test_reject_port_conflict(self, api_client, wdm_node):
        ch1 = WdmChannel.objects.create(wdm_node=wdm_node, grid_position=1, wavelength_nm="1560.61", label="C21")
        ch2 = WdmChannel.objects.create(wdm_node=wdm_node, grid_position=2, wavelength_nm="1559.79", label="C22")
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {str(ch1.pk): 100, str(ch2.pk): 100}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data

    def test_409_concurrent_edit(self, api_client, wdm_node):
        """A stale last_updated value triggers a 409 Conflict."""
        response = api_client.post(
            self._url(wdm_node.pk),
            {
                "last_updated": "2000-01-01 00:00:00+00:00",
                "mapping": {},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.data

    def test_unknown_channel_ignored(self, api_client, wdm_node):
        """Mapping entries for non-existent channel PKs are silently skipped."""
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {"99999": None}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["added"] == 0
        assert response.data["removed"] == 0
        assert response.data["changed"] == 0

    def test_empty_mapping(self, api_client, wdm_node):
        response = api_client.post(
            self._url(wdm_node.pk),
            {"mapping": {}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["added"] == 0
        assert response.data["removed"] == 0
        assert response.data["changed"] == 0
        assert "last_updated" in response.data


# ---------------------------------------------------------------------------
# WdmLinePort API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmLinePortAPI:
    base_url = "/api/plugins/wdm/wdm-line-ports/"

    def test_list(self, api_client, wdm_node):
        from dcim.models import RearPort

        rp = RearPort.objects.create(device=wdm_node.device, name="RP1", positions=1)
        WdmLinePort.objects.create(
            wdm_node=wdm_node,
            rear_port=rp,
            direction=WdmLineDirectionChoices.WEST,
        )
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, wdm_node):
        from dcim.models import RearPort

        rp = RearPort.objects.create(device=wdm_node.device, name="RP2", positions=1)
        tp = WdmLinePort.objects.create(
            wdm_node=wdm_node,
            rear_port=rp,
            direction=WdmLineDirectionChoices.WEST,
        )
        response = api_client.get(f"{self.base_url}{tp.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == tp.pk

    def test_create(self, api_client, wdm_node):
        from dcim.models import RearPort

        rp = RearPort.objects.create(device=wdm_node.device, name="RP3", positions=1)
        response = api_client.post(
            self.base_url,
            {
                "wdm_node": wdm_node.pk,
                "rear_port": rp.pk,
                "direction": WdmLineDirectionChoices.EAST,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_delete(self, api_client, wdm_node):
        from dcim.models import RearPort

        rp = RearPort.objects.create(device=wdm_node.device, name="RP4", positions=1)
        tp = WdmLinePort.objects.create(
            wdm_node=wdm_node,
            rear_port=rp,
            direction=WdmLineDirectionChoices.WEST,
        )
        response = api_client.delete(f"{self.base_url}{tp.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ---------------------------------------------------------------------------
# WdmChannel API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmChannelAPI:
    base_url = "/api/plugins/wdm/wdm-channels/"

    def test_list(self, api_client, channel):
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, channel):
        response = api_client.get(f"{self.base_url}{channel.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["label"] == "C21"
        assert response.data["status"] == WdmChannelStatusChoices.AVAILABLE

    def test_create(self, api_client, wdm_node):
        response = api_client.post(
            self.base_url,
            {
                "wdm_node": wdm_node.pk,
                "grid_position": 3,
                "wavelength_nm": "1558.98",
                "label": "C23",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["label"] == "C23"

    def test_update_status(self, api_client, channel):
        response = api_client.patch(
            f"{self.base_url}{channel.pk}/",
            {"status": WdmChannelStatusChoices.RESERVED},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == WdmChannelStatusChoices.RESERVED

    def test_delete(self, api_client, wdm_node):
        ch = WdmChannel.objects.create(
            wdm_node=wdm_node,
            grid_position=10,
            wavelength_nm="1550.12",
            label="C-DEL",
        )
        response = api_client.delete(f"{self.base_url}{ch.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_filter_by_wdm_node(self, api_client, channel, wdm_node):
        response = api_client.get(self.base_url, {"wdm_node_id": wdm_node.pk})
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["results"]]
        assert channel.pk in ids

    def test_filter_by_status(self, api_client, channel):
        response = api_client.get(self.base_url, {"status": WdmChannelStatusChoices.AVAILABLE})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1


# ---------------------------------------------------------------------------
# WdmCircuit API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmCircuitAPI:
    base_url = "/api/plugins/wdm/wdm-circuits/"

    def test_list(self, api_client, circuit):
        response = api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_retrieve(self, api_client, circuit):
        response = api_client.get(f"{self.base_url}{circuit.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Circuit"
        assert response.data["status"] == WdmCircuitStatusChoices.PLANNED

    def test_create(self, api_client):
        response = api_client.post(
            self.base_url,
            {
                "name": "New WDM Circuit",
                "status": WdmCircuitStatusChoices.PLANNED,
                "wavelength_nm": "1559.79",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New WDM Circuit"

    def test_update(self, api_client, circuit):
        response = api_client.patch(
            f"{self.base_url}{circuit.pk}/",
            {"description": "Updated circuit description"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description"] == "Updated circuit description"

    def test_delete(self, api_client):
        ckt = WdmCircuit.objects.create(
            name="Delete Me",
            status=WdmCircuitStatusChoices.PLANNED,
            wavelength_nm="1558.17",
        )
        response = api_client.delete(f"{self.base_url}{ckt.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_filter_by_status(self, api_client, circuit):
        response = api_client.get(self.base_url, {"status": WdmCircuitStatusChoices.PLANNED})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1


# ---------------------------------------------------------------------------
# stitch endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStitchAPI:
    def _url(self, circuit_pk):
        return f"/api/plugins/wdm/wdm-circuits/{circuit_pk}/stitch/"

    def test_stitch_empty_circuit(self, api_client, circuit):
        """A circuit with no path segments returns is_complete=False."""
        response = api_client.get(self._url(circuit.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["service_id"] == circuit.pk
        assert response.data["service_name"] == "Test Circuit"
        assert response.data["is_complete"] is False
        assert response.data["hops"] == []

    def test_stitch_with_channels(self, api_client, circuit, channel, wdm_node):
        """A circuit with path segments returns hops in sequence order."""
        WdmCircuitPath.objects.create(
            circuit=circuit,
            channel=channel,
            sequence=1,
        )
        response = api_client.get(self._url(circuit.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_complete"] is True
        assert len(response.data["hops"]) == 1
        hop = response.data["hops"][0]
        assert hop["channel_id"] == channel.pk
        assert hop["channel_label"] == channel.label
        assert hop["node_id"] == wdm_node.pk

    def test_stitch_response_shape(self, api_client, circuit):
        """Verify top-level keys are always present."""
        response = api_client.get(self._url(circuit.pk))
        assert response.status_code == status.HTTP_200_OK
        for key in ("service_id", "service_name", "wavelength_nm", "status", "is_complete", "hops"):
            assert key in response.data

    def test_stitch_wavelength_value(self, api_client, circuit):
        response = api_client.get(self._url(circuit.pk))
        assert response.status_code == status.HTTP_200_OK
        assert abs(response.data["wavelength_nm"] - 1560.61) < 0.01
