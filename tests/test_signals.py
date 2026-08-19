"""Tests for signal handlers."""

import pytest
from dcim.models import Cable, CablePath, Device, DeviceType, FrontPort, Interface, RearPort

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.testing import duplex_mux_pair
from netbox_wdm.testing.devices import create_duplex_mux, create_patch_panel
from netbox_wdm.trace import rebuild_wavelength_paths_for_node


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
        topo_a = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="T1-")
        topo_b = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="T2-")
        rebuild_wavelength_paths_for_node(topo_a.bundles["mux_a"].node)
        rebuild_wavelength_paths_for_node(topo_b.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 16

        # Light topology A's trunk: cable a client interface into CH1's mux
        # front port so a CablePath traversing the trunk cable exists.
        dt_client = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="Client-XCVR", slug="client-xcvr")
        client = Device.objects.create(
            site=wdm_site, device_type=dt_client, role=wdm_roles["wdm-mux"], name="T1-CLIENT"
        )
        iface = Interface.objects.create(device=client, name="xe-0/0/0", type="10gbase-x-sfpp")
        ch1 = topo_a.bundles["mux_a"].channels[0]
        client_cable = Cable(status="connected", a_terminations=[iface], b_terminations=[ch1.mux_front_port])
        client_cable.save()

        trunk = topo_a.cables[1]
        assert CablePath.objects.filter(_nodes__contains=trunk).exists()

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
        full-rebuild behavior rather than rebuilding nothing.
        """
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles, name_prefix="DK-")
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 8

        trunk = topo.cables[1]
        assert not CablePath.objects.filter(_nodes__contains=trunk).exists()

        rebuilt_pks: list[int] = []
        monkeypatch.setattr(
            "netbox_wdm.trace.rebuild_wavelength_paths_for_node", lambda node: rebuilt_pks.append(node.pk)
        )
        with django_capture_on_commit_callbacks(execute=True):
            trunk.delete()

        expected = {topo.bundles["mux_a"].node.pk, topo.bundles["mux_b"].node.pk}
        assert set(rebuilt_pks) == expected


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
        mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MS-MUX-A")
        mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "MS-MUX-B")
        pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "MS-PP-A")
        pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "MS-PP-B")

        # Patch cables only -- the mid-span PP-to-PP trunk is intentionally
        # missing, mirroring cable_duplex_through_pp_pair's termination order.
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
