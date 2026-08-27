# ITU Channel Plans

netbox-wdm ships with five built-in channel grids. The grid is set on each
[WDM profile](wdm-profiles.md) and propagated to every WdmNode created from
that profile. The grid drives both the channel labels (e.g. `C32`,
`L184.50`, `CWDM-1310`) and the wavelength assigned to each grid position.

## Grids supported

| Grid key | Display name | Channels | Spacing |
|---------|--------------|----------|---------|
| `dwdm_100ghz` | DWDM C-band 100 GHz | 44 | 100 GHz |
| `dwdm_50ghz`  | DWDM C-band 50 GHz | 88 | 50 GHz |
| `dwdm_l_100ghz` | DWDM L-band 100 GHz | 72 | 100 GHz |
| `dwdm_l_50ghz`  | DWDM L-band 50 GHz | 143 | 50 GHz |
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

## DWDM L-band 100 GHz

72 channels spanning 184.50 THz to 191.60 THz, with 100 GHz spacing. This
range is the ITU-T G.694.1 L-band (1565-1625 nm), anchored to the same
193.1 THz reference frequency as the C-band grids; 191.60 THz sits below
the C-band grid's 192.10 THz start, so the two bands do not overlap.
Labels are frequency-based with two decimal places and an `L` prefix.

| Position | Label | Frequency (THz) | Wavelength (nm, approx) |
|----------|-------|-----------------|-------------------------|
| 1 | L184.50 | 184.50 | 1624.89 |
| 2 | L184.60 | 184.60 | 1624.01 |
| ... | ... | ... | ... |
| 72 | L191.60 | 191.60 | 1564.68 |

## DWDM L-band 50 GHz

143 channels over the same 184.50 THz to 191.60 THz span, at 50 GHz
spacing. Labels are frequency-based with two decimal places and an `L`
prefix, incrementing by 0.05 THz per position.

| Position | Label | Frequency (THz) | Wavelength (nm, approx) |
|----------|-------|-----------------|-------------------------|
| 1 | L184.50 | 184.50 | 1624.89 |
| 2 | L184.55 | 184.55 | 1624.45 |
| ... | ... | ... | ... |
| 143 | L191.60 | 191.60 | 1564.68 |

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

## Picking the grid for a profile

The grid you set on a profile should describe what the hardware actually
is. The data sheet or front-panel labelling on the device tells you
which grid to pick:

- **CWDM:** front ports labelled by 20 nm wavelengths (typically `1270`
  through `1610`). 18 fixed wavelengths, no temperature stabilisation.
- **DWDM 100 GHz:** ports labelled with ITU C-band channel numbers
  (`C21` through `C64`) on a 100 GHz spacing.
- **DWDM 50 GHz:** 88 wavelengths on a 50 GHz spacing, with labels
  alternating `C{n}` and `C{n}.5`. Common on newer coherent line
  systems.
- **DWDM L-band 100 GHz / 50 GHz:** front ports labelled in the
  1565-1625 nm range, or by a frequency below 192 THz -- that is the
  giveaway when the data sheet speaks in wavelength rather than
  frequency. C+L systems pair an L-band mux with a C-band mux on the
  same fibre pair to double usable capacity; give each mux the profile
  that matches its own band, not the fibre as a whole.

If the device does not fit any of these, the bundled grids cannot
represent it; see [Adding a new grid](#adding-a-new-grid) below.

The grid is locked once channel plans exist. Changing it later requires
clearing the channel plans first or creating a new profile. In practice
this only comes up when a profile was set up with the wrong grid by
mistake -- the device's grid itself does not change.

## Adding a new grid

The grid list is hard-coded in `wdm_constants.py` and the
`WdmGridChoices` ChoiceSet. To add another (for example 25 GHz or
12.5 GHz spacing -- both allowed by ITU-T G.694.1, but rare on
fixed-grid hardware, which is why neither is bundled), extend both.

All four DWDM grids are built by one shared generator,
`_dwdm_channels(start_freq_thz, spacing_thz, count, label_fn)`, so a new
fixed grid is a start frequency, a spacing, a channel count, and a label
function -- reuse `_l_band_label` for a frequency-labelled grid, or write
a new one for a grid with its own channel numbering. Register the result
in `WDM_GRIDS` and add the matching key to `WdmGridChoices`. The `grid`
column stores the bare key string and no migration carries a CHOICES
literal, so adding a grid needs no migration. There is no runtime
customisation hook for grids today.
