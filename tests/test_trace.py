"""Tests for wavelength path tracing algorithm."""

from decimal import Decimal

import pytest
from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    PortMapping,
    RearPort,
    Site,
)

from netbox_wdm.choices import (
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmLineRoleChoices,
    WdmNodeTypeChoices,
)
from netbox_wdm.models import (
    WdmChannel,
    WdmLinePort,
    WdmNode,
    WdmWavelengthPath,
)
from netbox_wdm.trace import (
    _find_origin,
    _get_far_end_node,
    _get_rx_rear_port,
    _get_tx_rear_port,
    rebuild_wavelength_paths_for_node,
    trace_wavelength_path,
)


@pytest.fixture
def site():
    return Site.objects.create(name="Trace Test Site", slug="trace-test-site")


@pytest.fixture
def manufacturer():
    return Manufacturer.objects.create(name="Trace Mfg", slug="trace-mfg")


@pytest.fixture
def device_role():
    return DeviceRole.objects.create(name="Trace WDM Mux", slug="trace-wdm-mux")


def _create_mux_device(site, manufacturer, device_role, suffix):
    """Create a duplex MUX device with COM-TX, COM-RX rear ports and CH1/CH2 front ports."""
    dt = DeviceType.objects.create(
        manufacturer=manufacturer,
        model=f"Trace MUX {suffix}",
        slug=f"trace-mux-{suffix}",
    )
    device = Device.objects.create(
        name=f"MUX-{suffix}",
        site=site,
        device_type=dt,
        role=device_role,
    )

    # Create rear ports (COM-TX for transmit, COM-RX for receive) with 44 positions
    com_tx = RearPort.objects.create(device=device, name="COM-TX", positions=44, type="lc")
    com_rx = RearPort.objects.create(device=device, name="COM-RX", positions=44, type="lc")

    # Create front ports for CH1 and CH2 (MUX and DEMUX each)
    ch1_mux = FrontPort.objects.create(device=device, name="CH1-MUX", type="lc")
    ch1_demux = FrontPort.objects.create(device=device, name="CH1-DEMUX", type="lc")
    ch2_mux = FrontPort.objects.create(device=device, name="CH2-MUX", type="lc")
    ch2_demux = FrontPort.objects.create(device=device, name="CH2-DEMUX", type="lc")

    # Create port mappings (FrontPort <-> RearPort with positions)
    PortMapping.objects.create(device=device, front_port=ch1_mux, front_port_position=1, rear_port=com_tx, rear_port_position=1)
    PortMapping.objects.create(device=device, front_port=ch1_demux, front_port_position=1, rear_port=com_rx, rear_port_position=1)
    PortMapping.objects.create(device=device, front_port=ch2_mux, front_port_position=1, rear_port=com_tx, rear_port_position=2)
    PortMapping.objects.create(device=device, front_port=ch2_demux, front_port_position=1, rear_port=com_rx, rear_port_position=2)

    # Create WdmNode (skip auto-populate since there's no WdmProfile)
    node = WdmNode(
        device=device,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )
    # Use super().save() to skip auto-populate
    from netbox.models import NetBoxModel

    NetBoxModel.save(node)

    # Create line ports
    lp_tx = WdmLinePort.objects.create(
        wdm_node=node,
        rear_port=com_tx,
        direction=WdmLineDirectionChoices.COMMON,
        role=WdmLineRoleChoices.TX,
    )
    lp_rx = WdmLinePort.objects.create(
        wdm_node=node,
        rear_port=com_rx,
        direction=WdmLineDirectionChoices.EAST,
        role=WdmLineRoleChoices.RX,
    )

    # Create channels
    ch1 = WdmChannel(
        wdm_node=node,
        grid_position=1,
        wavelength_nm=Decimal("1530.33"),
        label="CH1",
        mux_front_port=ch1_mux,
        demux_front_port=ch1_demux,
    )
    NetBoxModel.save(ch1)

    ch2 = WdmChannel(
        wdm_node=node,
        grid_position=2,
        wavelength_nm=Decimal("1531.12"),
        label="CH2",
        mux_front_port=ch2_mux,
        demux_front_port=ch2_demux,
    )
    NetBoxModel.save(ch2)

    return {
        "device": device,
        "node": node,
        "com_tx": com_tx,
        "com_rx": com_rx,
        "lp_tx": lp_tx,
        "lp_rx": lp_rx,
        "ch1": ch1,
        "ch2": ch2,
        "ch1_mux": ch1_mux,
        "ch1_demux": ch1_demux,
        "ch2_mux": ch2_mux,
        "ch2_demux": ch2_demux,
    }


@pytest.fixture
def node_a(site, manufacturer, device_role):
    return _create_mux_device(site, manufacturer, device_role, "A")


@pytest.fixture
def node_b(site, manufacturer, device_role):
    return _create_mux_device(site, manufacturer, device_role, "B")


@pytest.mark.django_db
class TestGetTxRxRearPort:
    def test_get_tx_rear_port(self, node_a):
        rp = _get_tx_rear_port(node_a["node"])
        assert rp is not None
        assert rp.pk == node_a["com_tx"].pk

    def test_get_rx_rear_port(self, node_a):
        rp = _get_rx_rear_port(node_a["node"])
        assert rp is not None
        assert rp.pk == node_a["com_rx"].pk


@pytest.mark.django_db
class TestGetFarEndNode:
    def test_uncabled_returns_none(self, node_a):
        result = _get_far_end_node(node_a["com_tx"])
        assert result == (None, None)

    def test_cabled_returns_far_node(self, node_a, node_b):
        cable = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable.save()

        far_node, far_rp = _get_far_end_node(node_a["com_tx"])
        assert far_node is not None
        assert far_node.pk == node_b["node"].pk
        assert far_rp.pk == node_b["com_rx"].pk


@pytest.mark.django_db
class TestFindOrigin:
    def test_single_node_is_own_origin(self, node_a):
        origin = _find_origin(node_a["node"], grid_position=1)
        assert origin.pk == node_a["node"].pk

    def test_connected_finds_origin(self, node_a, node_b):
        # Cable A's TX to B's RX
        cable = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable.save()

        # From B, should walk back to A
        origin = _find_origin(node_b["node"], grid_position=1)
        assert origin.pk == node_a["node"].pk


@pytest.mark.django_db
class TestTraceSingleHop:
    def test_trace_single_hop(self, node_a, node_b):
        # Unidirectional: A TX -> B RX only
        cable1 = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable1.save()

        result = trace_wavelength_path(node_a["ch1"])
        assert len(result["channels"]) == 2
        assert result["channels"][0].pk == node_a["ch1"].pk
        assert result["channels"][1].pk == node_b["ch1"].pk

    def test_trace_returns_correct_order_from_far_end(self, node_a, node_b):
        # Unidirectional: A TX -> B RX only
        cable1 = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable1.save()

        # Trace from B's channel should find origin A and return A first
        result = trace_wavelength_path(node_b["ch1"])
        assert len(result["channels"]) == 2
        assert result["channels"][0].pk == node_a["ch1"].pk
        assert result["channels"][1].pk == node_b["ch1"].pk


@pytest.mark.django_db
class TestSingleNodeNoPath:
    def test_single_node_no_path(self, node_a):
        """Unconnected node should produce 0 wavelength paths."""
        rebuild_wavelength_paths_for_node(node_a["node"])
        assert WdmWavelengthPath.objects.count() == 0


@pytest.mark.django_db
class TestTwoConnectedNodes:
    def test_two_connected_nodes(self, node_a, node_b):
        """Cable A's TX->B's RX should produce 2 paths (one per grid position), each A->B."""
        cable1 = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable1.save()

        rebuild_wavelength_paths_for_node(node_a["node"])

        paths = WdmWavelengthPath.objects.all()
        assert paths.count() == 2

        for path in paths:
            entries = path.path_channels.select_related("channel__wdm_node").order_by("sequence")
            assert entries.count() == 2
            assert entries[0].channel.wdm_node.pk == node_a["node"].pk
            assert entries[1].channel.wdm_node.pk == node_b["node"].pk


@pytest.mark.django_db
class TestPathIsActive:
    def test_path_is_active_when_cables_connected(self, node_a, node_b):
        """Paths should be active when all cables have status=connected."""
        cable1 = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable1.save()

        result = trace_wavelength_path(node_a["ch1"])
        assert result["is_active"] is True


@pytest.mark.django_db
class TestPathCompleteness:
    def test_path_completeness(self, node_a, node_b):
        """Path is complete when both endpoints have client ports (mux or demux)."""
        cable1 = Cable(a_terminations=[node_a["com_tx"]], b_terminations=[node_b["com_rx"]])
        cable1.save()

        result = trace_wavelength_path(node_a["ch1"])
        assert result["is_complete"] is True
        assert len(result["channels"]) == 2
