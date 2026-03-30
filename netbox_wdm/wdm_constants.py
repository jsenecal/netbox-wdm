"""ITU grid constants for WDM channel plans."""

from __future__ import annotations

from decimal import Decimal

_SPEED_OF_LIGHT_KMS = Decimal("299792.458")

CWDM_CHANNELS: tuple[tuple[int, str, Decimal], ...] = tuple(
    (i + 1, f"CWDM-{1270 + i * 20}", Decimal(1270 + i * 20)) for i in range(18)
)

_DWDM_100GHZ_START_FREQ = Decimal("192.10")
_DWDM_100GHZ_SPACING = Decimal("0.10")
_DWDM_100GHZ_COUNT = 44
_DWDM_100GHZ_FIRST_CHANNEL = 21


def _dwdm_100ghz_channels() -> tuple[tuple[int, str, Decimal], ...]:
    channels: list[tuple[int, str, Decimal]] = []
    for i in range(_DWDM_100GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_100GHZ_SPACING
        wavelength_nm = (_SPEED_OF_LIGHT_KMS / freq_thz).quantize(Decimal("0.01"))
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i
        label = f"C{channel_num}"
        channels.append((i + 1, label, wavelength_nm))
    return tuple(channels)


DWDM_100GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_100ghz_channels()

_DWDM_50GHZ_SPACING = Decimal("0.05")
_DWDM_50GHZ_COUNT = 88


def _dwdm_50ghz_channels() -> tuple[tuple[int, str, Decimal], ...]:
    channels: list[tuple[int, str, Decimal]] = []
    for i in range(_DWDM_50GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_50GHZ_SPACING
        wavelength_nm = (_SPEED_OF_LIGHT_KMS / freq_thz).quantize(Decimal("0.01"))
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i // 2
        if i % 2 == 0:
            label = f"C{channel_num}"
        else:
            label = f"C{channel_num}.5"
        channels.append((i + 1, label, wavelength_nm))
    return tuple(channels)


DWDM_50GHZ_CHANNELS: tuple[tuple[int, str, Decimal], ...] = _dwdm_50ghz_channels()

WDM_GRIDS: dict[str, tuple[tuple[int, str, Decimal], ...]] = {
    "cwdm": CWDM_CHANNELS,
    "dwdm_100ghz": DWDM_100GHZ_CHANNELS,
    "dwdm_50ghz": DWDM_50GHZ_CHANNELS,
}

# Lookup dicts keyed by (grid, position) for fast access
_GRID_LOOKUP: dict[str, dict[int, tuple[str, Decimal]]] = {}
for _grid_key, _channels in WDM_GRIDS.items():
    _GRID_LOOKUP[_grid_key] = {pos: (label, wl) for pos, label, wl in _channels}


def get_channel_info(grid: str, position: int) -> tuple[str, Decimal]:
    """Return (label, wavelength_nm) for a grid type and position."""
    return _GRID_LOOKUP[grid][position]
