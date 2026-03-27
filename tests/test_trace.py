"""Tests for wavelength path tracing algorithm."""

import pytest
from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    FrontPortTemplate,
    Manufacturer,
    PortMapping,
    RearPort,
    RearPortTemplate,
    Site,
)
from dcim.models.device_component_templates import PortTemplateMapping

from netbox_wdm.choices import (
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmLineRoleChoices,
    WdmNodeTypeChoices,
)
from netbox_wdm.models import (
    WdmChannel,
    WdmChannelPlan,
    WdmLinePort,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
)
from netbox_wdm.trace import rebuild_wavelength_paths_for_node, trace_wavelength_path


def _create_cwdm_device(site, manufacturer, role, name):
    """Create a CWDM MUX device with COM-TX/COM-RX rear ports and channel front ports.

    Returns (device, profile, wdm_node) with channels created.
    The device type has 2 channels at CWDM grid positions 1 and 2.
    """
    dt = DeviceType.objects.create(
        manufacturer=manufacturer,
        model=f"CWDM-MUX-{name}",
        slug=f"cwdm-mux-{name.lower()}",
    )

    # Rear port templates
    rpt_tx = RearPortTemplate.objects.create(device_type=dt, name="COM-TX", positions=18, type="lc")
    rpt_rx = RearPortTemplate.objects.create(device_type=dt, name="COM-RX", positions=18, type="lc")

    # Front port templates for 2 channels
    fpt_ch1_mux = FrontPortTemplate.objects.create(device_type=dt, name="CH1-MUX", type="lc")
    fpt_ch1_demux = FrontPortTemplate.objects.create(device_type=dt, name="CH1-DEMUX", type="lc")
    fpt_ch2_mux = FrontPortTemplate.objects.create(device_type=dt, name="CH2-MUX", type="lc")
    fpt_ch2_demux = FrontPortTemplate.objects.create(device_type=dt, name="CH2-DEMUX", type="lc")

    # Port template mappings (NetBox 4.5+ style)
    PortTemplateMapping.objects.create(
        device_type=dt, front_port=fpt_ch1_mux, rear_port=rpt_tx, front_port_position=1, rear_port_position=1
    )
    PortTemplateMapping.objects.create(
        device_type=dt, front_port=fpt_ch1_demux, rear_port=rpt_rx, front_port_position=1, rear_port_position=1
    )
    PortTemplateMapping.objects.create(
        device_type=dt, front_port=fpt_ch2_mux, rear_port=rpt_tx, front_port_position=1, rear_port_position=2
    )
    PortTemplateMapping.objects.create(
        device_type=dt, front_port=fpt_ch2_demux, rear_port=rpt_rx, front_port_position=1, rear_port_position=2
    )

    # Create WDM profile with channel plans
    profile = WdmProfile.objects.create(
        device_type=dt,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.CWDM,
    )
    WdmChannelPlan.objects.create(
        profile=profile,
        grid_position=1,
        wavelength_nm=1270.00,
        label="CWDM-1270",
        mux_front_port_template=fpt_ch1_mux,
        demux_front_port_template=fpt_ch1_demux,
    )
    WdmChannelPlan.objects.create(
        profile=profile,
        grid_position=2,
        wavelength_nm=1290.00,
        label="CWDM-1290",
        mux_front_port_template=fpt_ch2_mux,
        demux_front_port_template=fpt_ch2_demux,
    )

    # Create device (auto-creates ports and port mappings from templates)
    device = Device.objects.create(name=name, site=site, device_type=dt, role=role)

    # Get ports
    com_tx = RearPort.objects.get(device=device, name="COM-TX")
    com_rx = RearPort.objects.get(device=device, name="COM-RX")
    ch1_mux = FrontPort.objects.get(device=device, name="CH1-MUX")
    ch1_demux = FrontPort.objects.get(device=device, name="CH1-DEMUX")
    ch2_mux = FrontPort.objects.get(device=device, name="CH2-MUX")
    ch2_demux = FrontPort.objects.get(device=device, name="CH2-DEMUX")

    # Ensure port mappings exist on the device instance
    for fp, rp, rp_pos in [
        (ch1_mux, com_tx, 1),
        (ch1_demux, com_rx, 1),
        (ch2_mux, com_tx, 2),
        (ch2_demux, com_rx, 2),
    ]:
        PortMapping.objects.get_or_create(
            device=device, front_port=fp, rear_port=rp,
            defaults={"front_port_position": 1, "rear_port_position": rp_pos},
        )

    # Create WDM node (skip auto-populate, we create channels manually)
    node = WdmNode.objects.create(
        device=device, node_type=WdmNodeTypeChoices.TERMINAL_MUX, grid=WdmGridChoices.CWDM
    )
    # Delete auto-populated channels (we want specific port assignments)
    node.channels.all().delete()

    # Create line ports
    WdmLinePort.objects.create(
        wdm_node=node, rear_port=com_tx, direction=WdmLineDirectionChoices.COMMON, role=WdmLineRoleChoices.TX
    )
    WdmLinePort.objects.create(
        wdm_node=node, rear_port=com_rx, direction=WdmLineDirectionChoices.COMMON, role=WdmLineRoleChoices.RX
    )

    # Create channels with port assignments
    WdmChannel.objects.create(wdm_node=node, grid_position=1, mux_front_port=ch1_mux, demux_front_port=ch1_demux)
    WdmChannel.objects.create(wdm_node=node, grid_position=2, mux_front_port=ch2_mux, demux_front_port=ch2_demux)

    return device, profile, node


@pytest.fixture
def site():
    return Site.objects.create(name="Trace Site", slug="trace-site")


@pytest.fixture
def manufacturer():
    return Manufacturer.objects.create(name="Trace Mfr", slug="trace-mfr")


@pytest.fixture
def role():
    return DeviceRole.objects.create(name="WDM Trace Role", slug="wdm-trace-role")


@pytest.mark.django_db
class TestSingleNodeNoPath:
    def test_single_node_no_path(self, site, manufacturer, role):
        """A single unconnected node produces no wavelength paths."""
        _, _, node = _create_cwdm_device(site, manufacturer, role, "Alone-A")
        rebuild_wavelength_paths_for_node(node)
        assert WdmWavelengthPath.objects.count() == 0


@pytest.mark.django_db
class TestTwoDirectlyConnectedNodes:
    def test_two_connected_nodes(self, site, manufacturer, role):
        """Two nodes connected directly produce wavelength paths."""
        dev_a, _, node_a = _create_cwdm_device(site, manufacturer, role, "Direct-A")
        dev_b, _, node_b = _create_cwdm_device(site, manufacturer, role, "Direct-B")

        # Cable A's COM-TX + COM-RX to B's COM-RX + COM-TX (trunk cable)
        a_tx = RearPort.objects.get(device=dev_a, name="COM-TX")
        a_rx = RearPort.objects.get(device=dev_a, name="COM-RX")
        b_tx = RearPort.objects.get(device=dev_b, name="COM-TX")
        b_rx = RearPort.objects.get(device=dev_b, name="COM-RX")

        Cable(a_terminations=[a_tx, a_rx], b_terminations=[b_rx, b_tx]).save()

        rebuild_wavelength_paths_for_node(node_a)

        paths = WdmWavelengthPath.objects.all()
        assert paths.count() == 2  # one per grid position

        path_1 = WdmWavelengthPath.objects.get(grid_position=1)
        channels = list(path_1.get_channels())
        assert len(channels) == 2
        node_pks = {ch.wdm_node.pk for ch in channels}
        assert node_a.pk in node_pks
        assert node_b.pk in node_pks


@pytest.mark.django_db
class TestTraceFunction:
    def test_trace_single_hop(self, site, manufacturer, role):
        """trace_wavelength_path returns ordered channels."""
        dev_a, _, node_a = _create_cwdm_device(site, manufacturer, role, "Trace-A")
        dev_b, _, node_b = _create_cwdm_device(site, manufacturer, role, "Trace-B")

        a_tx = RearPort.objects.get(device=dev_a, name="COM-TX")
        a_rx = RearPort.objects.get(device=dev_a, name="COM-RX")
        b_tx = RearPort.objects.get(device=dev_b, name="COM-TX")
        b_rx = RearPort.objects.get(device=dev_b, name="COM-RX")

        Cable(a_terminations=[a_tx, a_rx], b_terminations=[b_rx, b_tx]).save()

        ch_a = WdmChannel.objects.get(wdm_node=node_a, grid_position=1)
        result = trace_wavelength_path(ch_a)

        assert len(result["channels"]) == 2
        node_pks = {ch.wdm_node.pk for ch in result["channels"]}
        assert node_a.pk in node_pks
        assert node_b.pk in node_pks
        assert result["is_complete"] is True
        assert result["is_active"] is True
