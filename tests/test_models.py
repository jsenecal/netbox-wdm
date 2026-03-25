"""Tests for WDM models."""

import pytest
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.db import IntegrityError

from netbox_wdm.choices import WavelengthChannelStatusChoices, WdmFiberTypeChoices, WdmGridChoices, WdmNodeTypeChoices
from netbox_wdm.models import (
    WavelengthChannel,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


@pytest.fixture
def site():
    return Site.objects.create(name="Test Site", slug="test-site")


@pytest.fixture
def manufacturer():
    return Manufacturer.objects.create(name="Test Manufacturer", slug="test-manufacturer")


@pytest.fixture
def device_role():
    return DeviceRole.objects.create(name="WDM Mux", slug="wdm-mux")


@pytest.fixture
def device_type(manufacturer):
    return DeviceType.objects.create(
        manufacturer=manufacturer,
        model="Test MUX 44ch",
        slug="test-mux-44ch",
    )


@pytest.fixture
def device(site, device_type, device_role):
    return Device.objects.create(
        name="MUX-A",
        site=site,
        device_type=device_type,
        role=device_role,
    )


@pytest.fixture
def profile(device_type):
    return WdmDeviceTypeProfile.objects.create(
        device_type=device_type,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )


@pytest.mark.django_db
class TestWdmDeviceTypeProfile:
    def test_create(self, profile, device_type):
        assert profile.pk is not None
        assert profile.device_type == device_type
        assert profile.node_type == WdmNodeTypeChoices.TERMINAL_MUX

    def test_str(self, profile):
        assert "WDM Profile:" in str(profile)

    def test_get_absolute_url(self, profile):
        url = profile.get_absolute_url()
        assert "/plugins/wdm/" in url

    def test_fiber_type_default(self, profile):
        assert profile.fiber_type == WdmFiberTypeChoices.DUPLEX

    def test_fiber_type_single_fiber(self, device_type):
        # Delete existing profile first (from fixture)
        WdmDeviceTypeProfile.objects.filter(device_type=device_type).delete()
        p = WdmDeviceTypeProfile.objects.create(
            device_type=device_type,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
            fiber_type=WdmFiberTypeChoices.SINGLE_FIBER,
        )
        assert p.fiber_type == WdmFiberTypeChoices.SINGLE_FIBER

    def test_unique_device_type(self, profile, device_type):
        with pytest.raises(IntegrityError):
            WdmDeviceTypeProfile.objects.create(
                device_type=device_type,
                node_type=WdmNodeTypeChoices.ROADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWdmChannelTemplate:
    def test_create(self, profile):
        ct = WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert ct.pk is not None

    def test_str(self, profile):
        ct = WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert "C21" in str(ct)
        assert "1560.61" in str(ct)

    def test_unique_position(self, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        with pytest.raises(IntegrityError):
            WdmChannelTemplate.objects.create(
                profile=profile, grid_position=1, wavelength_nm=1559.79, label="C22"
            )


@pytest.mark.django_db
class TestWdmNode:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.pk is not None

    def test_str(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert "WDM:" in str(node)

    def test_auto_populate_channels_from_profile(self, device, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=2, wavelength_nm=1559.79, label="C22"
        )
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.channels.count() == 2

    def test_amplifier_no_auto_populate(self, device, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.AMPLIFIER,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.channels.count() == 0

    def test_unique_device(self, device):
        WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        with pytest.raises(IntegrityError):
            WdmNode.objects.create(
                device=device,
                node_type=WdmNodeTypeChoices.ROADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWavelengthChannel:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert ch.pk is not None
        assert ch.status == WavelengthChannelStatusChoices.AVAILABLE

    def test_str(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert "C21" in str(ch)


@pytest.mark.django_db
class TestValidateChannelMapping:
    def test_reject_lit_channel_remap(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
            status=WavelengthChannelStatusChoices.ACTIVE,
        )
        errors = WdmNode.validate_channel_mapping(node, {ch.pk: {"mux": 999, "demux": None}})
        assert len(errors) == 1
        assert "cannot be remapped" in errors[0]

    def test_reject_mux_port_conflict(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        ch2 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=2, wavelength_nm=1559.79, label="C22"
        )
        errors = WdmNode.validate_channel_mapping(node, {ch1.pk: {"mux": 100, "demux": None}, ch2.pk: {"mux": 100, "demux": None}})
        assert len(errors) == 1
        assert "Port conflict" in errors[0]
        assert "MUX" in errors[0]

    def test_reject_demux_port_conflict(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        ch2 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=2, wavelength_nm=1559.79, label="C22"
        )
        errors = WdmNode.validate_channel_mapping(node, {ch1.pk: {"mux": None, "demux": 200}, ch2.pk: {"mux": None, "demux": 200}})
        assert len(errors) == 1
        assert "Port conflict" in errors[0]
        assert "DEMUX" in errors[0]

    def test_valid_mapping(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        errors = WdmNode.validate_channel_mapping(node, {ch.pk: {"mux": 100, "demux": None}})
        assert errors == []
