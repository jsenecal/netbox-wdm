"""Tests for signal handlers."""

import pytest
from dcim.models import Cable, CablePath, Device, DeviceType, FrontPort, Interface, RearPort
from django.core.exceptions import ValidationError

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.signals import _pending_nodes
from netbox_wdm.testing import duplex_mux_pair
from netbox_wdm.testing.devices import create_duplex_mux, create_patch_panel


@pytest.mark.django_db
class TestCableDeletionScopedRebuild:
    def test_deleting_cable_rebuilds_only_affected_nodes(
        self, wdm_site, wdm_manufacturer, dt_cwdm_dx, dt_pp, wdm_roles, monkeypatch, django_capture_on_commit_callbacks
    ):
        """Regression test for issue #40 (deletion side).

        Deleting a cable must rebuild only the WDM nodes whose wavelength paths
        actually crossed it, not every node participating in any path. Two
        independent topologies are built; one trunk cable is lit by a client
        interface so a CablePath crossing it exists, then deleted. The second
        topology's nodes must not be rebuilt.
        """
        # Build both topologies inside a flushed block: their signals queue
        # rebuild work in the per-transaction dedup queue, and executing the
        # flush here drains it, so the delete block below observes only what
        # the deletion itself contributes.
        with django_capture_on_commit_callbacks(execute=True):
            topo_a = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="T1-")
            topo_b = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="T2-")
        # All four nodes flushed; duplex paths are directional, so each
        # topology holds 8 channels x 2 directions = 16 paths.
        assert WdmWavelengthPath.objects.count() == 32

        # Light topology A's trunk: cable a client interface into CH1's mux
        # front port so a CablePath traversing the trunk cable exists. Flushed
        # for the same reason as above.
        with django_capture_on_commit_callbacks(execute=True):
            dt_client = DeviceType.objects.create(
                manufacturer=wdm_manufacturer, model="Client-XCVR", slug="client-xcvr"
            )
            client = Device.objects.create(
                site=wdm_site, device_type=dt_client, role=wdm_roles["wdm-mux"], name="T1-CLIENT"
            )
            iface = Interface.objects.create(device=client, name="xe-0/0/0", type="10gbase-x-sfpp")
            ch1 = topo_a.bundles["mux_a"].channels[0]
            Cable(status="connected", a_terminations=[iface], b_terminations=[ch1.mux_front_port]).save()

        trunk = topo_a.cables[1]
        assert CablePath.objects.filter(_nodes__contains=trunk).exists()
        assert not _pending_nodes("rebuild"), "setup left rebuild work queued; the delete would drain it too"

        rebuilt_pks: list[int] = []
        monkeypatch.setattr(
            "netbox_wdm.trace.rebuild_wavelength_paths_for_node", lambda node: rebuilt_pks.append(node.pk)
        )
        with django_capture_on_commit_callbacks(execute=True):
            trunk.delete()

        expected = {topo_a.bundles["mux_a"].node.pk, topo_a.bundles["mux_b"].node.pk}
        untouched = {topo_b.bundles["mux_a"].node.pk, topo_b.bundles["mux_b"].node.pk}
        assert set(rebuilt_pks) == expected
        assert not set(rebuilt_pks) & untouched

    def test_deleting_dark_trunk_falls_back_to_full_rebuild(
        self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, monkeypatch, django_capture_on_commit_callbacks
    ):
        """Regression guard for issue #40: a dark trunk (no client lit, hence no
        CablePath row) cannot be scoped, so deleting it must keep the existing
        full-rebuild behavior -- every node participating in any wavelength
        path, including an unrelated topology's -- rather than rebuilding
        nothing.
        """
        with django_capture_on_commit_callbacks(execute=True):
            topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="DK-")
            other = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="DK2-")
        assert WdmWavelengthPath.objects.count() == 32

        trunk = topo.cables[1]
        assert not CablePath.objects.filter(_nodes__contains=trunk).exists()
        assert not _pending_nodes("rebuild"), "setup left rebuild work queued; the delete would drain it too"

        rebuilt_pks: list[int] = []
        monkeypatch.setattr(
            "netbox_wdm.trace.rebuild_wavelength_paths_for_node", lambda node: rebuilt_pks.append(node.pk)
        )
        with django_capture_on_commit_callbacks(execute=True):
            trunk.delete()

        all_pathed_nodes = {
            topo.bundles["mux_a"].node.pk,
            topo.bundles["mux_b"].node.pk,
            other.bundles["mux_a"].node.pk,
            other.bundles["mux_b"].node.pk,
        }
        assert set(rebuilt_pks) == all_pathed_nodes


@pytest.mark.django_db
class TestMidSpanCableCreation:
    def test_creating_mid_span_trunk_triggers_path_discovery(
        self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, django_capture_on_commit_callbacks
    ):
        """Regression test for issue #40 (creation side).

        A mid-span trunk cable between two patch panels terminates no WDM line
        port directly, but creating it completes the chain between two MUX
        nodes; wavelength paths must be discovered without waiting for an
        unrelated signal to fire.
        """
        # Devices and patch cables only -- the mid-span PP-to-PP trunk is
        # intentionally missing, mirroring cable_duplex_through_pp_pair's
        # termination order. Flushed so the queued rebuild work from this setup
        # drains here and the trunk block below stands on its own contribution.
        with django_capture_on_commit_callbacks(execute=True):
            mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MS-MUX-A")
            mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MS-MUX-B")
            pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "MS-PP-A")
            pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "MS-PP-B")
            Cable(
                status="connected",
                a_terminations=[mux_a.line_ports["tx"].rear_port, mux_a.line_ports["rx"].rear_port],
                b_terminations=[
                    FrontPort.objects.get(device=pp_a, name="FP-01"),
                    FrontPort.objects.get(device=pp_a, name="FP-02"),
                ],
            ).save()
            Cable(
                status="connected",
                a_terminations=[
                    FrontPort.objects.get(device=pp_b, name="FP-01"),
                    FrontPort.objects.get(device=pp_b, name="FP-02"),
                ],
                b_terminations=[mux_b.line_ports["rx"].rear_port, mux_b.line_ports["tx"].rear_port],
            ).save()
        assert WdmWavelengthPath.objects.count() == 0
        assert not _pending_nodes("rebuild"), "setup left rebuild work queued; the trunk would drain it too"

        with django_capture_on_commit_callbacks(execute=True):
            Cable(
                status="connected",
                a_terminations=[
                    RearPort.objects.get(device=pp_a, name="RP-01"),
                    RearPort.objects.get(device=pp_a, name="RP-02"),
                ],
                b_terminations=[
                    RearPort.objects.get(device=pp_b, name="RP-01"),
                    RearPort.objects.get(device=pp_b, name="RP-02"),
                ],
            ).save()

        # Both MUX nodes are rebuilt, and duplex paths are directional:
        # 8 channels x 2 directions = 16 paths (matching test_trace_duplex).
        assert WdmWavelengthPath.objects.count() == 16


@pytest.fixture
def mux_pair(wdm_site, dt_cwdm_dx, wdm_roles):
    """Two uncabled duplex MUX bundles."""
    mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "CLEAN-MUX-A")
    mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "CLEAN-MUX-B")
    return mux_a, mux_b


@pytest.mark.django_db
def test_cable_full_clean_rejects_tx_to_tx(mux_pair):
    """Regression test for issue #42: TX-to-TX trunk cabling must fail validation."""
    mux_a, mux_b = mux_pair
    cable = Cable(
        a_terminations=[mux_a.line_ports["tx"].rear_port],
        b_terminations=[mux_b.line_ports["tx"].rear_port],
    )
    with pytest.raises(ValidationError):
        cable.full_clean()


@pytest.mark.django_db
def test_cable_full_clean_rejects_rx_to_rx(mux_pair):
    """Regression test for issue #42: RX-to-RX trunk cabling must fail validation."""
    mux_a, mux_b = mux_pair
    cable = Cable(
        a_terminations=[mux_a.line_ports["rx"].rear_port],
        b_terminations=[mux_b.line_ports["rx"].rear_port],
    )
    with pytest.raises(ValidationError):
        cable.full_clean()


@pytest.mark.django_db
def test_cable_full_clean_allows_tx_to_rx(mux_pair):
    """TX-to-RX trunk cabling is valid and must pass full_clean."""
    mux_a, mux_b = mux_pair
    cable = Cable(
        a_terminations=[mux_a.line_ports["tx"].rear_port],
        b_terminations=[mux_b.line_ports["rx"].rear_port],
    )
    cable.full_clean()


@pytest.mark.django_db
def test_cable_full_clean_duplex_pairing_by_index(mux_pair):
    """Duplex cables pair terminations by index: [TX, RX] to [RX, TX] is valid, [TX, RX] to [TX, RX] is not."""
    mux_a, mux_b = mux_pair
    a_tx = mux_a.line_ports["tx"].rear_port
    a_rx = mux_a.line_ports["rx"].rear_port
    b_tx = mux_b.line_ports["tx"].rear_port
    b_rx = mux_b.line_ports["rx"].rear_port

    valid = Cable(a_terminations=[a_tx, a_rx], b_terminations=[b_rx, b_tx])
    valid.full_clean()

    invalid = Cable(a_terminations=[a_tx, a_rx], b_terminations=[b_tx, b_rx])
    with pytest.raises(ValidationError):
        invalid.full_clean()


@pytest.mark.django_db
def test_cable_full_clean_ignores_non_wdm_terminations(wdm_site, dt_pp, wdm_roles, mux_pair):
    """Terminations not managed by a WdmLinePort pass through untouched."""
    from dcim.models import FrontPort, RearPort

    mux_a, _ = mux_pair
    pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "CLEAN-PP-A")
    pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "CLEAN-PP-B")

    # Patch-panel trunk: two rear ports, neither is a WDM line port.
    trunk = Cable(
        a_terminations=[RearPort.objects.get(device=pp_a, name="RP-01")],
        b_terminations=[RearPort.objects.get(device=pp_b, name="RP-01")],
    )
    trunk.full_clean()

    # WDM trunk rear port into a patch-panel front port: only one side is WDM-managed.
    patch = Cable(
        a_terminations=[mux_a.line_ports["tx"].rear_port],
        b_terminations=[FrontPort.objects.get(device=pp_a, name="FP-01")],
    )
    patch.full_clean()
