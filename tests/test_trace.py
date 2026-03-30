"""Tests for wavelength path tracing algorithm."""

import pytest

from netbox_wdm.models import WdmWavelengthPath
from netbox_wdm.testing import duplex_mux_pair, dwdm_mux_to_roadm, sf_mux_pair
from netbox_wdm.testing.devices import create_duplex_mux
from netbox_wdm.trace import rebuild_wavelength_paths_for_node, trace_wavelength_path


@pytest.mark.django_db
class TestSingleNodeNoPath:
    def test_unconnected_node_has_no_paths(self, wdm_site, dt_cwdm_dx, wdm_roles):
        bundle = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "Lone-MUX")
        rebuild_wavelength_paths_for_node(bundle.node)
        assert WdmWavelengthPath.objects.count() == 0


@pytest.mark.django_db
class TestDuplexMuxPairThroughPP:
    def test_discovers_paths(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 8  # 8 CWDM channels

    def test_path_has_both_nodes(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        path = WdmWavelengthPath.objects.first()
        channels = list(path.get_channels())
        assert len(channels) == 2
        node_pks = {ch.wdm_node.pk for ch in channels}
        assert topo.bundles["mux_a"].node.pk in node_pks
        assert topo.bundles["mux_b"].node.pk in node_pks

    def test_paths_are_complete_and_active(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        for path in WdmWavelengthPath.objects.all():
            assert path.is_complete is True
            assert path.is_active is True


@pytest.mark.django_db
class TestSFMuxPairThroughPP:
    def test_discovers_paths(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        assert WdmWavelengthPath.objects.count() == 8

    def test_path_has_both_nodes(self, wdm_site, dt_cwdm_sf, dt_pp, wdm_roles):
        topo = sf_mux_pair(wdm_site, dt_cwdm_sf, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux_a"].node)
        path = WdmWavelengthPath.objects.first()
        channels = list(path.get_channels())
        assert len(channels) == 2


@pytest.mark.django_db
class TestDWDMMuxToROADMThroughPP:
    def test_discovers_paths(self, wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles):
        topo = dwdm_mux_to_roadm(wdm_site, dt_dwdm, dt_roadm, dt_pp, wdm_roles)
        rebuild_wavelength_paths_for_node(topo.bundles["mux"].node)
        # ROADM has 20 channels, MUX has 44 — only shared grid positions form paths
        assert WdmWavelengthPath.objects.count() == 20


@pytest.mark.django_db
class TestTraceFunction:
    def test_trace_returns_correct_structure(self, wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
        topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
        ch = topo.bundles["mux_a"].channels[0]
        result = trace_wavelength_path(ch)
        assert len(result.channels) == 2
        assert result.is_complete is True
        assert result.is_active is True
