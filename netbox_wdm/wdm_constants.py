"""ITU grid constants for WDM channel plans."""

_SPEED_OF_LIGHT_KMS = 299792.458

CWDM_CHANNELS: tuple[tuple[int, str, float], ...] = tuple(
    (i + 1, f"CWDM-{1270 + i * 20}", float(1270 + i * 20)) for i in range(18)
)

_DWDM_100GHZ_START_FREQ = 192.10
_DWDM_100GHZ_SPACING = 0.10
_DWDM_100GHZ_COUNT = 44
_DWDM_100GHZ_FIRST_CHANNEL = 21


def _dwdm_100ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_100GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_100GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i
        label = f"C{channel_num}"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_100GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_100ghz_channels()

_DWDM_50GHZ_SPACING = 0.05
_DWDM_50GHZ_COUNT = 88


def _dwdm_50ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_50GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_50GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i // 2
        if i % 2 == 0:
            label = f"C{channel_num}"
        else:
            label = f"C{channel_num}.5"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_50GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_50ghz_channels()

WDM_GRIDS: dict[str, tuple[tuple[int, str, float], ...]] = {
    "cwdm": CWDM_CHANNELS,
    "dwdm_100ghz": DWDM_100GHZ_CHANNELS,
    "dwdm_50ghz": DWDM_50GHZ_CHANNELS,
}
