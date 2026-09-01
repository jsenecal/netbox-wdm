import importlib
from decimal import Decimal

import pytest

from netbox_wdm.choices import WdmGridChoices
from netbox_wdm.wdm_constants import (
    CWDM_CHANNELS,
    DWDM_C_50GHZ_CHANNELS,
    DWDM_C_100GHZ_CHANNELS,
    DWDM_L_50GHZ_CHANNELS,
    DWDM_L_100GHZ_CHANNELS,
    WDM_GRIDS,
    get_channel_info,
)


class TestCwdmChannels:
    def test_channel_count(self):
        assert len(CWDM_CHANNELS) == 18

    def test_first_channel(self):
        pos, label, wl = CWDM_CHANNELS[0]
        assert pos == 1
        assert label == "CWDM-1270"
        assert wl == Decimal("1270")

    def test_last_channel(self):
        pos, label, wl = CWDM_CHANNELS[-1]
        assert pos == 18
        assert label == "CWDM-1610"
        assert wl == Decimal("1610")

    def test_spacing(self):
        for i in range(1, len(CWDM_CHANNELS)):
            assert CWDM_CHANNELS[i][2] - CWDM_CHANNELS[i - 1][2] == Decimal("20")


class TestDwdm100GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_C_100GHZ_CHANNELS) == 44

    def test_first_channel(self):
        pos, label, wl = DWDM_C_100GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"
        assert isinstance(wl, Decimal)

    def test_last_channel(self):
        pos, label, wl = DWDM_C_100GHZ_CHANNELS[-1]
        assert pos == 44
        assert label == "C64"

    def test_labels_sequential(self):
        for i, (_, label, _) in enumerate(DWDM_C_100GHZ_CHANNELS):
            assert label == f"C{21 + i}"


class TestDwdm50GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_C_50GHZ_CHANNELS) == 88

    def test_first_channel(self):
        pos, label, wl = DWDM_C_50GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"

    def test_half_channel_labels(self):
        _, label, _ = DWDM_C_50GHZ_CHANNELS[1]
        assert label == "C21.5"


class TestDwdmL100GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_L_100GHZ_CHANNELS) == 72

    def test_first_channel(self):
        pos, label, wl = DWDM_L_100GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "L184.50"
        assert wl == Decimal("1624.89")

    def test_last_channel(self):
        pos, label, wl = DWDM_L_100GHZ_CHANNELS[-1]
        assert pos == 72
        assert label == "L191.60"
        assert wl == Decimal("1564.68")


class TestDwdmL50GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_L_50GHZ_CHANNELS) == 143

    def test_first_channel(self):
        pos, label, wl = DWDM_L_50GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "L184.50"
        assert wl == Decimal("1624.89")

    def test_interleaved_second_channel(self):
        _, label, _ = DWDM_L_50GHZ_CHANNELS[1]
        assert label == "L184.55"

    def test_last_channel(self):
        pos, label, wl = DWDM_L_50GHZ_CHANNELS[-1]
        assert pos == 143
        assert label == "L191.60"
        assert wl == Decimal("1564.68")


# CWDM is excluded where a rule holds only for the frequency-derived grids.
DWDM_GRID_KEYS = ("dwdm_c_100ghz", "dwdm_c_50ghz", "dwdm_l_100ghz", "dwdm_l_50ghz")

# Each pair is (100 GHz grid, 50 GHz grid) within one band.
BAND_GRID_PAIRS = (("dwdm_c_100ghz", "dwdm_c_50ghz"), ("dwdm_l_100ghz", "dwdm_l_50ghz"))


class TestWdmGrids:
    def test_every_selectable_grid_has_a_channel_table(self):
        """A grid in the ChoiceSet but not in WDM_GRIDS fails silently.

        WdmChannel.label and .wavelength_nm swallow the resulting KeyError and
        render blank, so the two enumerations drifting apart would surface as
        unlabelled channels in the UI rather than as an error anywhere.
        """
        assert set(WDM_GRIDS) == set(WdmGridChoices.values())

    def test_grid_rename_migration_targets_current_keys(self):
        """The C-band rename migration must land rows on keys that still resolve.

        A typo in either column is silent: WdmChannel.label swallows the
        KeyError from an unresolvable grid and renders blank, so a bad rename
        target would blank every channel on the affected nodes.
        """
        module = importlib.import_module("netbox_wdm.migrations.0012_rename_c_band_grid_keys")
        old_keys = {old for old, _new in module.GRID_RENAMES}
        new_keys = {new for _old, new in module.GRID_RENAMES}
        assert new_keys <= set(WDM_GRIDS)
        assert not old_keys & set(WDM_GRIDS)

    def test_grid_references(self):
        assert WDM_GRIDS["cwdm"] is CWDM_CHANNELS
        assert WDM_GRIDS["dwdm_c_100ghz"] is DWDM_C_100GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_c_50ghz"] is DWDM_C_50GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_l_100ghz"] is DWDM_L_100GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_l_50ghz"] is DWDM_L_50GHZ_CHANNELS

    def test_l_band_resolvable_via_get_channel_info(self):
        assert get_channel_info("dwdm_l_100ghz", 1) == DWDM_L_100GHZ_CHANNELS[0][1:]
        assert get_channel_info("dwdm_l_50ghz", 143) == DWDM_L_50GHZ_CHANNELS[-1][1:]

    def test_l_band_and_c_band_do_not_overlap(self):
        wl_c = {ch[2] for ch in DWDM_C_100GHZ_CHANNELS} | {ch[2] for ch in DWDM_C_50GHZ_CHANNELS}
        wl_l = {ch[2] for ch in DWDM_L_100GHZ_CHANNELS} | {ch[2] for ch in DWDM_L_50GHZ_CHANNELS}
        assert not wl_c & wl_l

    @pytest.mark.parametrize("grid_key", WDM_GRIDS.keys())
    def test_positions_sequential(self, grid_key):
        positions = [ch[0] for ch in WDM_GRIDS[grid_key]]
        assert positions == list(range(1, len(positions) + 1))

    @pytest.mark.parametrize("grid_key", DWDM_GRID_KEYS)
    def test_wavelengths_decreasing(self, grid_key):
        channels = WDM_GRIDS[grid_key]
        for i in range(1, len(channels)):
            assert channels[i][2] < channels[i - 1][2]

    @pytest.mark.parametrize(("coarse_key", "fine_key"), BAND_GRID_PAIRS)
    def test_100ghz_channels_are_subset_of_50ghz(self, coarse_key, fine_key):
        wl_fine = {ch[2] for ch in WDM_GRIDS[fine_key]}
        for ch in WDM_GRIDS[coarse_key]:
            assert ch[2] in wl_fine

    @pytest.mark.parametrize("grid_key", WDM_GRIDS.keys())
    def test_channel_tuple_structure(self, grid_key):
        for pos, label, wl in WDM_GRIDS[grid_key]:
            assert isinstance(pos, int)
            assert isinstance(label, str)
            assert isinstance(wl, Decimal)
            assert pos > 0
            assert len(label) > 0
            assert wl > 0
