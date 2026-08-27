"""ITU grid constants for WDM channel plans."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

_SPEED_OF_LIGHT_KMS = Decimal("299792.458")

CWDM_CHANNELS: tuple[tuple[int, str, Decimal], ...] = tuple(
    (i + 1, f"CWDM-{1270 + i * 20}", Decimal(1270 + i * 20)) for i in range(18)
)


def _dwdm_channels(
    start_freq_thz: Decimal,
    spacing_thz: Decimal,
    count: int,
    label_fn: Callable[[int, Decimal], str],
) -> tuple[tuple[int, str, Decimal], ...]:
    """Build a fixed-grid DWDM channel table.

    Frequencies step up from `start_freq_thz` by `spacing_thz` for `count`
    channels, so wavelengths descend as the position ascends. `label_fn`
    receives the zero-based index and the channel's frequency so callers can
    label channels either by ITU channel number (C-band) or directly by
    frequency (L-band).
    """
    channels: list[tuple[int, str, Decimal]] = []
    for i in range(count):
        freq_thz = start_freq_thz + i * spacing_thz
        wavelength_nm = (_SPEED_OF_LIGHT_KMS / freq_thz).quantize(Decimal("0.01"))
        channels.append((i + 1, label_fn(i, freq_thz), wavelength_nm))
    return tuple(channels)


# Channel pitch is a property of the spacing, not of the band: 100 GHz is
# 0.10 THz in the C-band and the L-band alike.
_SPACING_100GHZ = Decimal("0.10")
_SPACING_50GHZ = Decimal("0.05")

# C-band 100 GHz / 50 GHz fixed grids, anchored per ITU-T G.694.1 at 193.1 THz.
# Channel numbering starts at C21 (192.10 THz), which is also where the 50 GHz
# grid starts; that grid interleaves a ".5" channel between each pair of
# 100 GHz channels.
_DWDM_C_START_FREQ = Decimal("192.10")
_DWDM_C_FIRST_CHANNEL = 21
_DWDM_C_100GHZ_COUNT = 44
_DWDM_C_50GHZ_COUNT = 88


def _c_band_100ghz_label(i: int, freq_thz: Decimal) -> str:
    return f"C{_DWDM_C_FIRST_CHANNEL + i}"


def _c_band_50ghz_label(i: int, freq_thz: Decimal) -> str:
    channel_num = _DWDM_C_FIRST_CHANNEL + i // 2
    return f"C{channel_num}" if i % 2 == 0 else f"C{channel_num}.5"


DWDM_100GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_channels(
    _DWDM_C_START_FREQ, _SPACING_100GHZ, _DWDM_C_100GHZ_COUNT, _c_band_100ghz_label
)
DWDM_50GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_channels(
    _DWDM_C_START_FREQ, _SPACING_50GHZ, _DWDM_C_50GHZ_COUNT, _c_band_50ghz_label
)

# L-band 100 GHz / 50 GHz fixed grids. The L-band spans 1565-1625 nm, which on
# the ITU-T G.694.1 grid anchored at 193.1 THz runs 184.50-191.60 THz -- both
# endpoints fall exactly on the grid, and 191.60 THz sits below the C-band
# grid's 192.10 THz start, so the two bands never share a wavelength. Unlike
# the C-band grids, L-band channels have no assigned ITU channel numbers in
# common use, so labels are frequency-based instead.
_DWDM_L_START_FREQ = Decimal("184.50")
_DWDM_L_100GHZ_COUNT = 72
_DWDM_L_50GHZ_COUNT = 143


def _l_band_label(i: int, freq_thz: Decimal) -> str:
    return f"L{freq_thz:.2f}"


DWDM_L_100GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_channels(
    _DWDM_L_START_FREQ, _SPACING_100GHZ, _DWDM_L_100GHZ_COUNT, _l_band_label
)
DWDM_L_50GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_channels(
    _DWDM_L_START_FREQ, _SPACING_50GHZ, _DWDM_L_50GHZ_COUNT, _l_band_label
)

WDM_GRIDS: dict[str, tuple[tuple[int, str, Decimal], ...]] = {
    "cwdm": CWDM_CHANNELS,
    "dwdm_100ghz": DWDM_100GHZ_CHANNELS,
    "dwdm_50ghz": DWDM_50GHZ_CHANNELS,
    "dwdm_l_100ghz": DWDM_L_100GHZ_CHANNELS,
    "dwdm_l_50ghz": DWDM_L_50GHZ_CHANNELS,
}

# Lookup dicts keyed by (grid, position) for fast access
_GRID_LOOKUP: dict[str, dict[int, tuple[str, Decimal]]] = {}
for _grid_key, _channels in WDM_GRIDS.items():
    _GRID_LOOKUP[_grid_key] = {pos: (label, wl) for pos, label, wl in _channels}


def get_channel_info(grid: str, position: int) -> tuple[str, Decimal]:
    """Return (label, wavelength_nm) for a grid type and position."""
    return _GRID_LOOKUP[grid][position]
