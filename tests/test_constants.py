import pytest

from netbox_wdm.wdm_constants import (
    CWDM_CHANNELS,
    DWDM_100GHZ_CHANNELS,
    DWDM_50GHZ_CHANNELS,
    WDM_GRIDS,
)


class TestCwdmChannels:
    def test_channel_count(self):
        assert len(CWDM_CHANNELS) == 18

    def test_first_channel(self):
        pos, label, wl = CWDM_CHANNELS[0]
        assert pos == 1
        assert label == "CWDM-1270"
        assert wl == 1270.0

    def test_last_channel(self):
        pos, label, wl = CWDM_CHANNELS[-1]
        assert pos == 18
        assert label == "CWDM-1610"
        assert wl == 1610.0

    def test_spacing(self):
        for i in range(1, len(CWDM_CHANNELS)):
            assert CWDM_CHANNELS[i][2] - CWDM_CHANNELS[i - 1][2] == 20.0

    def test_positions_sequential(self):
        positions = [ch[0] for ch in CWDM_CHANNELS]
        assert positions == list(range(1, 19))


class TestDwdm100GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_100GHZ_CHANNELS) == 44

    def test_first_channel(self):
        pos, label, wl = DWDM_100GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"
        assert isinstance(wl, float)

    def test_last_channel(self):
        pos, label, wl = DWDM_100GHZ_CHANNELS[-1]
        assert pos == 44
        assert label == "C64"

    def test_labels_sequential(self):
        for i, (_, label, _) in enumerate(DWDM_100GHZ_CHANNELS):
            assert label == f"C{21 + i}"

    def test_positions_sequential(self):
        positions = [ch[0] for ch in DWDM_100GHZ_CHANNELS]
        assert positions == list(range(1, 45))

    def test_wavelengths_decreasing(self):
        for i in range(1, len(DWDM_100GHZ_CHANNELS)):
            assert DWDM_100GHZ_CHANNELS[i][2] < DWDM_100GHZ_CHANNELS[i - 1][2]


class TestDwdm50GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_50GHZ_CHANNELS) == 88

    def test_first_channel(self):
        pos, label, wl = DWDM_50GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"

    def test_half_channel_labels(self):
        _, label, _ = DWDM_50GHZ_CHANNELS[1]
        assert label == "C21.5"

    def test_positions_sequential(self):
        positions = [ch[0] for ch in DWDM_50GHZ_CHANNELS]
        assert positions == list(range(1, 89))

    def test_wavelengths_decreasing(self):
        for i in range(1, len(DWDM_50GHZ_CHANNELS)):
            assert DWDM_50GHZ_CHANNELS[i][2] < DWDM_50GHZ_CHANNELS[i - 1][2]

    def test_100ghz_channels_are_subset(self):
        wl_50 = {ch[2] for ch in DWDM_50GHZ_CHANNELS}
        for ch in DWDM_100GHZ_CHANNELS:
            assert ch[2] in wl_50


class TestWdmGrids:
    def test_all_grids_present(self):
        assert set(WDM_GRIDS.keys()) == {"cwdm", "dwdm_100ghz", "dwdm_50ghz"}

    def test_grid_references(self):
        assert WDM_GRIDS["cwdm"] is CWDM_CHANNELS
        assert WDM_GRIDS["dwdm_100ghz"] is DWDM_100GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_50ghz"] is DWDM_50GHZ_CHANNELS

    @pytest.mark.parametrize("grid_key", WDM_GRIDS.keys())
    def test_channel_tuple_structure(self, grid_key):
        for pos, label, wl in WDM_GRIDS[grid_key]:
            assert isinstance(pos, int)
            assert isinstance(label, str)
            assert isinstance(wl, float)
            assert pos > 0
            assert len(label) > 0
            assert wl > 0
