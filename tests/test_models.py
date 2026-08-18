"""Tests for WDM models."""

import pytest
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from netbox_wdm.choices import WdmChannelStatusChoices, WdmFiberTypeChoices, WdmGridChoices, WdmNodeTypeChoices
from netbox_wdm.models import (
    WdmChannel,
    WdmChannelPlan,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
    WdmWavelengthPathChannel,
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
    return WdmProfile.objects.create(
        device_type=device_type,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )


@pytest.mark.django_db
class TestWdmProfile:
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
        WdmProfile.objects.filter(device_type=device_type).delete()
        p = WdmProfile.objects.create(
            device_type=device_type,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
            fiber_type=WdmFiberTypeChoices.SINGLE_FIBER,
        )
        assert p.fiber_type == WdmFiberTypeChoices.SINGLE_FIBER

    def test_unique_device_type(self, profile, device_type):
        with pytest.raises(IntegrityError):
            WdmProfile.objects.create(
                device_type=device_type,
                node_type=WdmNodeTypeChoices.ROADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWdmChannelPlan:
    def test_create(self, profile):
        cp = WdmChannelPlan.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert cp.pk is not None

    def test_str(self, profile):
        cp = WdmChannelPlan.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert "C21" in str(cp)
        assert "1560.61" in str(cp)

    def test_unique_position(self, profile):
        WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21")
        with pytest.raises(IntegrityError):
            WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm=1559.79, label="C22")


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
        WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21")
        WdmChannelPlan.objects.create(profile=profile, grid_position=2, wavelength_nm=1559.79, label="C22")
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.channels.count() == 2

    def test_amplifier_no_auto_populate(self, device, profile):
        WdmChannelPlan.objects.create(profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21")
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
class TestWdmChannel:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(
            wdm_node=node,
            grid_position=1,
        )
        assert ch.pk is not None
        assert ch.status == WdmChannelStatusChoices.AVAILABLE

    def test_str(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(
            wdm_node=node,
            grid_position=1,
        )
        assert "C21" in str(ch)

    def test_module_scoped_channel_requires_effective_grid(self, device, manufacturer):
        """A module-scoped channel needs a grid from somewhere: either its module's
        ModuleType has a WdmProfile, or the node's own grid is set. Neither here, so
        clean() must reject it instead of leaving a channel that 500s on render."""
        node = WdmNode.objects.create(device=device)  # blank grid
        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="No-Profile-MT")
        bay = ModuleBay.objects.create(device=device, name="MB1")
        module = Module.objects.create(device=device, module_bay=bay, module_type=module_type)
        ch = WdmChannel(wdm_node=node, module=module, grid_position=1)
        with pytest.raises(ValidationError):
            ch.full_clean()

    def test_label_and_wavelength_degrade_when_grid_unresolvable(self, device, manufacturer):
        """A pre-existing channel can end up with no resolvable grid (e.g. its
        module's WdmProfile was deleted after the channel was created). label and
        wavelength_nm must degrade to "" / None instead of raising KeyError, so the
        row still renders."""
        node = WdmNode.objects.create(device=device)  # blank grid
        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="No-Profile-MT-2")
        bay = ModuleBay.objects.create(device=device, name="MB2")
        module = Module.objects.create(device=device, module_bay=bay, module_type=module_type)
        ch = WdmChannel(wdm_node=node, module=module, grid_position=1)

        assert ch.label == ""
        assert ch.wavelength_nm is None
        assert str(ch)  # __str__ must not raise either


@pytest.mark.django_db
class TestValidateChannelMapping:
    def test_reject_lit_channel_remap(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            status=WdmChannelStatusChoices.ACTIVE,
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
        ch1 = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        ch2 = WdmChannel.objects.create(wdm_node=node, grid_position=2)
        errors = WdmNode.validate_channel_mapping(
            node, {ch1.pk: {"mux": 100, "demux": None}, ch2.pk: {"mux": 100, "demux": None}}
        )
        assert len(errors) == 1
        assert "Port conflict" in errors[0]
        assert "MUX" in errors[0]

    def test_reject_demux_port_conflict(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        ch2 = WdmChannel.objects.create(wdm_node=node, grid_position=2)
        errors = WdmNode.validate_channel_mapping(
            node, {ch1.pk: {"mux": None, "demux": 200}, ch2.pk: {"mux": None, "demux": 200}}
        )
        assert len(errors) == 1
        assert "Port conflict" in errors[0]
        assert "DEMUX" in errors[0]

    def test_valid_mapping(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        errors = WdmNode.validate_channel_mapping(node, {ch.pk: {"mux": 100, "demux": None}})
        assert errors == []

    def test_reject_cross_module_port(self, device, manufacturer):
        """A FrontPort belonging to a different module than the channel is rejected."""
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="Cassette")
        bay = ModuleBay.objects.create(device=device, name="MUX1", position="MUX1")
        module = Module.objects.create(device=device, module_bay=bay, module_type=module_type)
        ch = WdmChannel.objects.create(wdm_node=node, module=module, grid_position=1)
        # FrontPort belongs to no module, while the channel is module-scoped: mismatch.
        other_fp = FrontPort.objects.create(device=device, name="OTHER1", type="lc-upc", positions=1)

        errors = WdmNode.validate_channel_mapping(node, {ch.pk: {"mux": other_fp.pk, "demux": None}})
        assert len(errors) == 1
        assert "does not belong to channel" in errors[0]
        assert "MUX" in errors[0]


@pytest.mark.django_db
class TestWdmWavelengthPath:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        path = WdmWavelengthPath.objects.create(
            grid_position=1, wavelength_nm=1560.61, is_complete=True, is_active=True
        )
        WdmWavelengthPathChannel.objects.create(path=path, channel=ch, sequence=1)
        assert path.pk is not None
        assert path.path_channels.count() == 1

    def test_str(self, device):
        path = WdmWavelengthPath.objects.create(
            grid_position=1, wavelength_nm=1560.61, is_complete=False, is_active=False
        )
        assert "1560.61" in str(path)

    def test_channel_delete_cascades_path_entries(self, device):
        """Wavelength paths are derived data, not a source of truth: deleting a
        channel that is part of one must not be blocked, it should simply take
        its path-channel entry down with it."""
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        path = WdmWavelengthPath.objects.create(
            grid_position=1, wavelength_nm=1560.61, is_complete=True, is_active=True
        )
        WdmWavelengthPathChannel.objects.create(path=path, channel=ch, sequence=1)
        ch.delete()
        assert not WdmWavelengthPathChannel.objects.filter(path=path).exists()

    def test_unique_path_sequence(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        ch2 = WdmChannel.objects.create(wdm_node=node, grid_position=2)
        path = WdmWavelengthPath.objects.create(
            grid_position=1, wavelength_nm=1560.61, is_complete=True, is_active=True
        )
        WdmWavelengthPathChannel.objects.create(path=path, channel=ch1, sequence=1)
        with pytest.raises(IntegrityError):
            WdmWavelengthPathChannel.objects.create(path=path, channel=ch2, sequence=1)

    def test_get_ordered_channels(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        ch2 = WdmChannel.objects.create(wdm_node=node, grid_position=2)
        path = WdmWavelengthPath.objects.create(
            grid_position=1, wavelength_nm=1560.61, is_complete=True, is_active=True
        )
        WdmWavelengthPathChannel.objects.create(path=path, channel=ch2, sequence=2)
        WdmWavelengthPathChannel.objects.create(path=path, channel=ch1, sequence=1)
        ordered = list(path.get_channels())
        assert ordered[0] == ch1
        assert ordered[1] == ch2
