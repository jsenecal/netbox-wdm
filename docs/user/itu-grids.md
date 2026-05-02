# ITU Channel Plans

netbox-wdm ships with three built-in channel grids. The grid is set on each
[WDM profile](wdm-profiles.md) and propagated to every WdmNode created from
that profile. The grid drives both the channel labels (e.g. `C32`,
`CWDM-1310`) and the wavelength assigned to each grid position.

## Grids supported

| Grid key | Display name | Channels | Spacing |
|---------|--------------|----------|---------|
| `dwdm_100ghz` | DWDM C-band 100 GHz | 44 | 100 GHz |
| `dwdm_50ghz`  | DWDM C-band 50 GHz | 88 | 50 GHz |
| `cwdm`        | CWDM | 18 | 20 nm |

The constants are defined in `netbox_wdm/wdm_constants.py`. Wavelengths are
computed from frequency for DWDM grids and held as a fixed list for CWDM.

## How grid_position maps to a channel

The `grid_position` field on `WdmChannelPlan` and `WdmChannel` is a 1-based
integer that indexes into the grid's channel list. The plugin uses
`get_channel_info(grid, position)` to look up the matching `(label,
wavelength_nm)` tuple.

`grid_position` also drives the `rear_port_position` value used in
PortMappings. This is what lets multiple channels share a single COM rear
port: each channel's PortMapping points at the same rear_port but carries a
different `rear_port_position`. EXP and 1310 pass-through ports are
positioned **after** the channel positions on the same COM rear port.

## DWDM 100 GHz

44 channels starting from 192.10 THz, with 100 GHz spacing. Labels are
`C21` through `C64` (the ITU C-band convention).

| Position | Label | Frequency (THz) | Wavelength (nm, approx) |
|----------|-------|-----------------|-------------------------|
| 1 | C21 | 192.10 | 1560.61 |
| 2 | C22 | 192.20 | 1559.79 |
| ... | ... | ... | ... |
| 44 | C64 | 196.40 | 1526.44 |

Wavelengths are computed as `c / freq_thz` and rounded to two decimal places
using `Decimal` arithmetic so values are stable across processes.

## DWDM 50 GHz

88 channels, 50 GHz spacing, labels alternate between `C{n}` and `C{n}.5`.
Position 1 starts at 192.10 THz (label `C21`), position 2 is 192.15 THz
(label `C21.5`), and so on through position 88.

## CWDM

18 channels with a fixed 20 nm spacing.

| Position | Label | Wavelength (nm) |
|----------|-------|-----------------|
| 1 | CWDM-1270 | 1270 |
| 2 | CWDM-1290 | 1290 |
| 3 | CWDM-1310 | 1310 |
| 4 | CWDM-1330 | 1330 |
| ... | ... | ... |
| 18 | CWDM-1610 | 1610 |

## Choosing a grid

- **CWDM:** cheapest optics, widest spacing, no temperature stabilisation.
  Best for fixed-wavelength access plant or short metro spans. Limited to 18
  channels and not amplifier-friendly outside the C-band subset.
- **DWDM 100 GHz:** the workhorse for metro and regional. 44 channels in the
  C-band with off-the-shelf coloured optics.
- **DWDM 50 GHz:** double the channels at half the spacing. Used when 100
  GHz is exhausted or when running coherent muxponders that fit comfortably
  in a 50 GHz slot.

You cannot change a profile's grid after channel plans exist; either remove
the channel plans first, or create a new profile.

## Adding a new grid

The grid list is hard-coded in `wdm_constants.py` and the
`WdmGridChoices` ChoiceSet. To add another (for example L-band 100 GHz),
extend both: append the grid to `WDM_GRIDS`, add a key to `WdmGridChoices`,
and update the migrations if you keep CHOICES literals in `models.py`. There
is no runtime customisation hook for grids today.
