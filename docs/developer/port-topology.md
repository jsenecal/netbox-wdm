# Port Topology

This page is the developer-facing companion to the user-facing
[DeviceType Setup](../user/device-types.md) recipes. It covers the
position-stack contract that ties WDM channels to NetBox port mappings,
the per-hardware port layouts the plugin understands, and the rules a new
DeviceType must obey to participate in cable tracing.

## Position-stack contract

The plugin uses one integer to bridge ITU and NetBox: `grid_position`.

- `WdmChannelPlan.grid_position` records the channel's index in the ITU
  grid (1-based).
- `WdmChannel.grid_position` is copied from the plan at auto-population
  time and never drifts across the overlay.
- Every `dcim.PortMapping` the plugin emits sets
  `rear_port_position = channel.grid_position`. NetBox's `dcim.CablePath`
  picks the right per-channel front port back out of a shared trunk by
  comparing this against the cable's `position` on the rear port side.

The single rule a DeviceType must obey is therefore:

> Every PortTemplateMapping's `rear_port_position` must equal the
> `grid_position` of the channel it carries.

`PortTemplateMapping` rows live on the DeviceType and are how NetBox
materialises `PortMapping` rows when a Device is created. Mismatched
positions break tracing silently because cables continue to terminate but
no longer pick up the right per-channel port on the far side.

## EXP, 1310, and other pass-through ports

Real hardware exposes pass-through ports (EXP for upgrade chains, 1310 for
gray-light injection) that share the **same** trunk fibres as the
WDM-multiplexed channels. The plugin models them as ordinary
FrontPortTemplate plus PortTemplateMapping rows on the DeviceType, but at
**positions after** the channel positions on the same COM rear ports.

For an N-channel CWDM duplex MUX, RearPortTemplate `positions` is set to
`N + 2` and the PortTemplateMappings stack like this:

| `rear_port_position` | Front port (mux side) | Front port (demux side) |
|----------------------|------------------------|--------------------------|
| 1 | `CH1-MUX` | `CH1-DEMUX` |
| ... | ... | ... |
| N | `CHN-MUX` | `CHN-DEMUX` |
| N + 1 | `EXP-MUX` | `EXP-DEMUX` |
| N + 2 | `1310-MUX` | `1310-DEMUX` |

These pass-through ports are deliberately **not** part of any
`WdmChannelPlan`. They have no `WdmChannel` row, no PROTECT guard, and no
representation in the wavelength editor. The port-sync hash also excludes
them, so a cable plugged into EXP without an accompanying channel does
not raise drift.

The trace can still **follow** an EXP cable like any other, because the
PortTemplateMapping puts the EXP front port behind the same COM rear port.
This is what lets operators run an upgrade fibre into an existing MUX
without modelling it in the WDM layer.

## Hardware classes

The factories under `netbox_wdm.testing.device_types` are reference
implementations of every layout below. They use `get_or_create`, so they
are safe to run more than once.

### Duplex terminal MUX

Two trunk fibres (`COM-TX` + `COM-RX`); per-channel client ports split
into a MUX (TX) leg and a DEMUX (RX) leg. The DEMUX leg is what makes
this a duplex profile and is what fills `WdmChannelPlan.demux_front_port_template`.

- RearPortTemplates: `COM-TX`, `COM-RX`, both with `positions = N + extras`.
- FrontPortTemplates: `CH{n}-MUX` and `CH{n}-DEMUX` per channel, plus
  `EXP-MUX/DEMUX` and `1310-MUX/DEMUX` if present.
- PortTemplateMappings: `CH{n}-MUX -> COM-TX @ n`,
  `CH{n}-DEMUX -> COM-RX @ n`, EXP and 1310 at trailing positions.

For DWDM hardware the per-channel front ports are usually named after
the ITU label (`C21-MUX`, `C21-DEMUX`, ...). The factory
`create_dwdm_mux_dx_type` follows that convention.

### Single-fibre terminal MUX

One trunk fibre (`COM`) carrying both directions; per-channel client
ports are bidirectional `CH{n}` front ports. `WdmChannelPlan.demux_front_port_template`
is **null** on every plan row.

- RearPortTemplate: `COM` with `positions = N + extras`.
- FrontPortTemplates: `CH{n}` per channel, plus `EXP` and `1310`.
- PortTemplateMappings: `CH{n} -> COM @ n`, EXP/1310 at trailing positions.

The plugin reflects this through `WdmFiberTypeChoices.SINGLE_FIBER` on
the profile. The wavelength editor hides its DEMUX column for these
profiles; the trace visualisation collapses TX and RX onto a single fibre.

### 2-degree ROADM

Four trunk fibres (`LINE-EAST-TX/RX`, `LINE-WEST-TX/RX`); a pool of
ADD/DROP front ports that the wavelength editor rebinds to channels at
runtime.

- RearPortTemplates: `LINE-{EAST,WEST}-{TX,RX}`, each with `positions =
  full grid` (44 for DWDM 100 GHz, 88 for DWDM 50 GHz).
- FrontPortTemplates: `ADD-{nn}` and `DROP-{nn}` per intended channel
  count.
- PortTemplateMappings: `ADD-{nn} -> LINE-EAST-TX @ nn`,
  `DROP-{nn} -> LINE-EAST-RX @ nn` by convention. The mappings only
  define the **default** binding; the wavelength editor rewrites the
  derived `dcim.PortMapping` rows when an operator assigns ADDs and
  DROPs to a different channel.

A higher-degree ROADM follows the same shape -- one TX/RX
RearPortTemplate per direction.

### Inline amplifier (EDFA)

One LINE-IN front port, one LINE-OUT rear port, one PortTemplateMapping
linking them. No per-channel ports.

`_auto_populate_channels()` skips amplifier nodes, so no
`WdmChannelPlan` rows are needed. This is why the WDM model can let an
amplifier participate in the cable plant trace without owning any
channel objects of its own.

### Fibre patch panel

1:1 FrontPort to RearPort mappings, no profile.

The trace identifies a patch panel by the absence of a `WdmLinePort` on
the RearPort and the presence of a PortMapping out the front. This is
the same path-following logic used to enter and exit any pass-through
device.

## Line ports

`WdmLinePort` is how the trace identifies trunk RearPorts. It is **not**
auto-created -- per-Device line ports are user-managed (see
[WDM Nodes](../user/wdm-nodes.md#line-ports)).

The pair `(direction, role)` is a uniqueness key per node. The trace uses
`role` to filter outbound vs inbound walks (TX/BIDI for forward, RX/BIDI
for backward) and uses `direction` together with the topological position
of the rear port to decide which TX is the "right" one to follow on
multi-degree nodes.

The full enum lists are in `netbox_wdm/choices.py`:

- `WdmLineDirectionChoices`: `common`, `east`, `west` (extensible to N/S
  for future higher-degree ROADMs).
- `WdmLineRoleChoices`: `tx`, `rx`, `bidi`.

## Validation rules

The plugin enforces these at save time:

- `WdmLinePort.rear_port` must belong to the same Device as the
  `WdmLinePort.wdm_node.device`.
- `WdmLinePort` cannot duplicate another row on the same node by either
  `rear_port` or `(direction, role)`.
- `WdmChannel` cannot reuse a `grid_position` on the same node.
- `WdmChannelPlan.mux_front_port_template` and
  `demux_front_port_template` must reference FrontPortTemplates on the
  profile's DeviceType.
- A duplex profile rejects null `demux_front_port_template`. A
  single-fibre profile rejects non-null `demux_front_port_template`.

These constraints are how the overlay stays internally consistent: a
DeviceType the plugin accepts is one whose ports it can map back to
channels deterministically.

## Adding a new hardware class

To support a new hardware class:

1. Decide whether it fits one of `terminal_mux`, `oadm`, `roadm`,
   `amplifier`. If not, extend `WdmNodeTypeChoices` first.
2. Decide whether channels are auto-populated. If not (as for amplifiers),
   add the type to the early-return branch in
   `WdmNode._auto_populate_channels()`.
3. Decide the trunk shape: how many RearPorts, what direction/role each
   carries, whether duplex or single-fibre.
4. Build a factory in `netbox_wdm/testing/device_types.py` that creates
   the templates and mappings. Keep the position stack honest -- channel
   positions first, pass-through positions after.
5. If the new class introduces a different per-degree topology, extend
   the trace to recognise it. The current code is direction-agnostic for
   anything beyond 2-degree (it tries every TX line port until one
   reaches an unvisited node), so most new shapes work without code
   changes.

## Where to look in code

| Concern | File |
|---------|------|
| ITU grid tables | `netbox_wdm/wdm_constants.py` |
| Choice enums | `netbox_wdm/choices.py` |
| Profile, channel plan, node, line port, channel models | `netbox_wdm/models.py` |
| Auto-population | `WdmNode._auto_populate_channels` in `netbox_wdm/models.py` |
| DeviceType factories | `netbox_wdm/testing/device_types.py` |
| Device factories | `netbox_wdm/testing/devices.py` |
