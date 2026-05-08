# DeviceType Setup

netbox-wdm overlays NetBox's existing DCIM stack instead of replacing it.
That means before the plugin can do anything useful, the underlying NetBox
DeviceType must be laid out with the right FrontPortTemplate,
RearPortTemplate, and PortTemplateMapping rows -- the plugin does **not**
auto-generate port templates.

This page is a recipe book. Pick the section that matches your hardware,
follow the template list, and you end up with a DeviceType the plugin can
build a [WDM profile](wdm-profiles.md) on top of.

## The setup chain

For every WDM device type, the boilerplate falls in this order:

1. Create the **DeviceType** with the right model, manufacturer, slug, and
   `u_height`.
2. Create **RearPortTemplates** for the trunk side. Set `positions` to at
   least the number of channels the hardware multiplexes; add extra
   positions for any pass-through ports (EXP, 1310, gray) that share the
   same trunk.
3. Create **FrontPortTemplates** for every per-channel client port plus
   any pass-through client ports.
4. Create **PortTemplateMappings** linking each FrontPortTemplate to the
   correct RearPortTemplate at the correct `rear_port_position`. The
   position number is what aligns the channel grid with the trunk fibre
   ordering.
5. Create the **WdmProfile** on the DeviceType ([WDM Profiles](wdm-profiles.md)).
6. Create one **WdmChannelPlan** per ITU position the hardware carries,
   pointing at the matching FrontPortTemplate(s).

After steps 1-6 the DeviceType is ready. When you create a Device of that
DeviceType, the plugin auto-creates a `WdmNode` and one `WdmChannel` per
plan. You then need one more manual step per device: see
[Creating line ports](#creating-line-ports) below.

## Position alignment

There is one rule that ties the whole stack together:

> **Every PortTemplateMapping's `rear_port_position` must match the
> `grid_position` of the channel it carries.**

The plugin uses `grid_position` as the bridge between the ITU grid and
NetBox's `dcim.CablePath`. When a PortMapping is emitted (during
`apply-mapping` or port sync), it sets
`rear_port_position = channel.grid_position`. Cable tracing then picks the
right channel's front port back out of a shared trunk. Keep these numbers
aligned at template time and the runtime side cannot get confused.

EXP, 1310, gray, and any other pass-through ports use the **same** COM
rear ports but at positions **after** the channel positions. Allocate
RearPortTemplate `positions` to cover both. The port-sync hash deliberately
ignores pass-through ports, so they will not raise drift warnings on their
own.

## Recipe: duplex terminal MUX

A duplex MUX has two trunk fibres (one TX, one RX) and per-channel client
ports split into a MUX (TX) leg and a DEMUX (RX) leg.

For an N-channel CWDM duplex MUX with EXP and 1310 pass-through:

| Object | Name | Type | Positions | Notes |
|--------|------|------|-----------|-------|
| RearPortTemplate | `COM-TX` | `lc-apc` | N + 2 | trunk TX |
| RearPortTemplate | `COM-RX` | `lc-apc` | N + 2 | trunk RX |
| FrontPortTemplate | `CH1-MUX` ... `CHN-MUX` | `lc-upc` | -- | per-channel TX |
| FrontPortTemplate | `CH1-DEMUX` ... `CHN-DEMUX` | `lc-upc` | -- | per-channel RX |
| FrontPortTemplate | `EXP-MUX`, `EXP-DEMUX` | `lc-upc` | -- | pass-through |
| FrontPortTemplate | `1310-MUX`, `1310-DEMUX` | `lc-upc` | -- | gray-light pass-through |

PortTemplateMappings (one per channel, plus EXP and 1310):

| Front port | Rear port | rear_port_position |
|------------|-----------|--------------------|
| `CH{n}-MUX` | `COM-TX` | n |
| `CH{n}-DEMUX` | `COM-RX` | n |
| `EXP-MUX` | `COM-TX` | N + 1 |
| `EXP-DEMUX` | `COM-RX` | N + 1 |
| `1310-MUX` | `COM-TX` | N + 2 |
| `1310-DEMUX` | `COM-RX` | N + 2 |

WdmProfile fields:

- `node_type = terminal_mux`
- `grid = cwdm` (or `dwdm_100ghz`, `dwdm_50ghz`)
- `fiber_type = duplex`

WdmChannelPlan rows (one per channel slot the hardware carries, **not**
including the pass-through ports):

- `grid_position = n`
- `mux_front_port_template = CH{n}-MUX`
- `demux_front_port_template = CH{n}-DEMUX`
- `wavelength_nm` and `label` from the [ITU table](itu-grids.md) for that
  position.

For DWDM devices the convention is to name the front ports after the ITU
label (`C21-MUX`, `C21-DEMUX`, ...) instead of `CH{n}`. The plugin does
not care about the names; only the channel-plan link to the right
FrontPortTemplate matters.

## Recipe: single-fibre terminal MUX

Single-fibre (BiDi) hardware uses one bidirectional trunk fibre and one
bidirectional client front port per channel.

| Object | Name | Type | Positions |
|--------|------|------|-----------|
| RearPortTemplate | `COM` | `lc-apc` | N + extras |
| FrontPortTemplate | `CH1` ... `CHN` | `lc-upc` | -- |
| FrontPortTemplate | `EXP`, `1310` | `lc-upc` | -- |

PortTemplateMappings:

| Front port | Rear port | rear_port_position |
|------------|-----------|--------------------|
| `CH{n}` | `COM` | n |
| `EXP` | `COM` | N + 1 |
| `1310` | `COM` | N + 2 |

WdmProfile:

- `node_type = terminal_mux`
- `grid = cwdm`
- `fiber_type = single_fiber`

WdmChannelPlan rows:

- `mux_front_port_template = CH{n}`
- `demux_front_port_template = null` (single fibre uses MUX only)

For single-fibre profiles the [Wavelength Editor](wavelength-editor.md)
hides the DEMUX column and the [trace visualisation](circuit-trace.md)
shows one fibre per cable.

## Recipe: 2-degree ROADM

A ROADM has two trunk directions (EAST and WEST) each with a TX and RX
fibre, plus a pool of ADD/DROP client ports that the wavelength editor
can rebind to any channel.

| Object | Name | Type | Positions |
|--------|------|------|-----------|
| RearPortTemplate | `LINE-EAST-TX` | `lc-apc` | full grid (e.g. 44 for DWDM 100 GHz) |
| RearPortTemplate | `LINE-EAST-RX` | `lc-apc` | full grid |
| RearPortTemplate | `LINE-WEST-TX` | `lc-apc` | full grid |
| RearPortTemplate | `LINE-WEST-RX` | `lc-apc` | full grid |
| FrontPortTemplate | `ADD-01` ... `ADD-NN` | `lc-upc` | -- |
| FrontPortTemplate | `DROP-01` ... `DROP-NN` | `lc-upc` | -- |

PortTemplateMappings (one ADD/DROP pair per channel position you want
wavelengths on; bind to the EAST line by convention):

| Front port | Rear port | rear_port_position |
|------------|-----------|--------------------|
| `ADD-{n:02d}` | `LINE-EAST-TX` | n |
| `DROP-{n:02d}` | `LINE-EAST-RX` | n |

The mappings only describe the **default** binding. Operators rebind ADDs
and DROPs to specific channels live via the
[Wavelength Editor](wavelength-editor.md), which rewrites the
PortTemplateMapping-derived `dcim.PortMapping` rows on the device.

WdmProfile:

- `node_type = roadm`
- `grid = dwdm_100ghz` (or whatever grid the optics support)
- `fiber_type = duplex`

WdmChannelPlan rows: one per ITU position, with `ADD-{nn}` as
`mux_front_port_template` and `DROP-{nn}` as `demux_front_port_template`.

Higher-degree ROADMs follow the same shape: one TX and one RX
RearPortTemplate per direction, named `LINE-{direction}-TX` and
`LINE-{direction}-RX`.

## Recipe: inline amplifier (EDFA)

An EDFA passes the full multiplex through unchanged. There is no
per-channel client port and the WDM profile skips channel auto-population
entirely.

| Object | Name | Type | Positions |
|--------|------|------|-----------|
| FrontPortTemplate | `LINE-IN` | `lc-apc` | -- |
| RearPortTemplate | `LINE-OUT` | `lc-apc` | 1 |
| PortTemplateMapping | `LINE-IN` -> `LINE-OUT` | -- | `rear_port_position = 1` |

WdmProfile:

- `node_type = amplifier`
- `grid` matches the optics it carries
- `fiber_type` matches the surrounding plant

No WdmChannelPlan rows are required for amplifiers; they pass every
wavelength on the trunk. `_auto_populate_channels()` skips amplifier
nodes, so you do not need to repeat the channel-plan list per device.

For bidirectional amplifier modules, build a separate FrontPort/RearPort
pair for each direction with its own PortTemplateMapping.

## Recipe: fibre patch panel

Patch panels have **no** WDM profile. They are just NetBox patch panels
with 1:1 FrontPort to RearPort mappings, but they show up in WDM trace
diagrams whenever a wavelength path passes through them.

| Object | Name | Type | Positions |
|--------|------|------|-----------|
| FrontPortTemplate | `FP-01` ... `FP-NN` | `lc-upc` | -- |
| RearPortTemplate | `RP-01` ... `RP-NN` | `lc-apc` | 1 each |
| PortTemplateMapping | `FP-{n:02d}` -> `RP-{n:02d}` | -- | `rear_port_position = 1` |

There is no profile, no channel plan, and no line port to create -- a
patch panel is invisible to the WDM models, only the cable plant sees it.

## Creating line ports

`WdmLinePort` rows tag the device's trunk RearPorts with a direction and
role so the trace can know which side of the device a wavelength enters
or leaves on. They are **not** auto-created -- you must add them manually
once the Device exists.

For each WDM device, in **WDM > Line Ports > Add**:

| Hardware | Rear port | direction | role |
|----------|-----------|-----------|------|
| Duplex MUX | `COM-TX` | `common` | `tx` |
| Duplex MUX | `COM-RX` | `common` | `rx` |
| Single-fibre MUX | `COM` | `common` | `bidi` |
| 2-degree ROADM | `LINE-EAST-TX` | `east` | `tx` |
| 2-degree ROADM | `LINE-EAST-RX` | `east` | `rx` |
| 2-degree ROADM | `LINE-WEST-TX` | `west` | `tx` |
| 2-degree ROADM | `LINE-WEST-RX` | `west` | `rx` |
| EDFA | `LINE-OUT` | `common` | `bidi` |

The same DeviceType produces line ports identically every time, so this is
the place where bulk-import via CSV pays off if you provision many
identical devices. The constraint engine prevents two line ports on the
same node from sharing a rear port or from having the same
`(direction, role)` pair.

Patch panels do not need line ports.

## Common pitfalls

- **`positions` too small on a RearPortTemplate.** If the trunk rear port
  has fewer positions than your channel count plus pass-through ports,
  some `rear_port_position` values will be invalid and the corresponding
  PortTemplateMappings will refuse to save.
- **Forgot the `EXP` and `1310` mappings.** They are not required for the
  plugin to work, but if you cable to them and they have no template
  mapping, NetBox cable tracing stops there.
- **Channel plan rows pointing at the wrong DeviceType.** A
  `WdmChannelPlan.mux_front_port_template` must reference a
  FrontPortTemplate on the **same** DeviceType as the profile. The form
  filters its choices, but bulk imports need to be careful.
- **Duplex profile with `demux_front_port_template = null`.** This is
  rejected at validation time. Single-fibre profiles must omit the demux
  template; duplex profiles must populate both.
- **Renaming a FrontPortTemplate after devices exist.** Existing FrontPort
  instances on real Devices are not renamed automatically, so the
  `_auto_populate_channels()` lookup by name will miss them on the next
  device created from that DeviceType. See [Port Sync](port-sync.md).

## Pre-built recipes in code

If you provision DeviceTypes from a script or a fixture rather than
through the UI, the helpers in `netbox_wdm.testing` are reference
implementations of every recipe above. They are part of the public test
package and can be imported by your own setup code:

```python
from netbox_wdm.testing import (
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_dwdm_mux_dx_type,
    create_edfa_type,
    create_fiber_pp_type,
    create_roadm_2d_type,
)
```

Each helper creates the templates, mappings, profile, and channel plans
in a single call. They are idempotent (`get_or_create`), so running them
twice does not duplicate rows.
