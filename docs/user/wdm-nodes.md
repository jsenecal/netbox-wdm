# WDM Nodes

A **WDM node** is the per-device instance of a [WDM profile](wdm-profiles.md).
It is a one-to-one overlay on `dcim.Device` and owns the actual `WdmChannel`
and `WdmLinePort` rows for that device.

## Lifecycle

Nodes are normally created automatically. When a `dcim.Device` is saved and
its DeviceType has a WDM profile, a `post_save` signal handler schedules a
`WdmNode` to be created on transaction commit, copying `node_type` and `grid`
from the profile.

You can also create a WdmNode manually from **WDM > Nodes > Add**, selecting
the device. This is useful when a device was imported before its DeviceType
got a profile.

When a WdmNode is created, `_auto_populate_channels()` runs:

1. The profile's `WdmChannelPlan` rows are loaded.
2. For each plan, the plugin looks up `FrontPort` instances on the new device
   by name (matching the plan's `mux_front_port_template.name` and
   `demux_front_port_template.name`).
3. One `WdmChannel` is bulk-created per plan, with foreign keys to the
   matching front ports.

If a front port template name does not match an existing FrontPort on the
device (for example because port templates were renamed after device
creation), the channel is still created with a null front port. You can fix
this later via [Port Sync](port-sync.md).

Amplifier nodes (`node_type=amplifier`) skip channel auto-population because
amplifiers do not carry per-channel client ports.

## Fields

| Field | Notes |
|-------|-------|
| `device` | One-to-one to `dcim.Device` |
| `node_type` | `terminal_mux`, `oadm`, `roadm`, `amplifier` |
| `grid` | Same choices as `WdmProfile.grid` |
| `description` | Free text |
| `expected_port_hash` | Internal: SHA-256 of the expected PortMapping state |
| `port_sync_valid` | Internal: True when actual PortMappings match expected hash |

The two internal fields are explained in [Port Sync](port-sync.md).

## Fixed vs. ROADM nodes

The model distinguishes between **fixed** and **ROADM** nodes via the
`is_fixed` property:

- `is_fixed = True` for `terminal_mux`, `oadm`, and `amplifier`. The
  channel-to-port assignments and line port configuration are hardware
  determined; modifying them is rejected at `save()` time.
- `is_fixed = False` for `roadm`. Channel assignments can be remapped at
  runtime, and the [Wavelength Editor](wavelength-editor.md) is exposed as
  a tab on the node detail page.

For fixed nodes, only `WdmChannel.status` (Available / Reserved / Active) can
be changed after creation.

## Detail page

The WDM Node detail page shows:

- A header with port-sync status. When out of sync, a banner lets operators
  trigger Sync Now.
- A stacked status bar across all channels showing
  active / reserved / available split, broken into connected and disconnected
  buckets (a channel is "connected" when at least one of its MUX or DEMUX
  front ports has a cable).
- A **Channels** tab listing every `WdmChannel` on the node.
- A **Line Ports** tab listing every `WdmLinePort` (the trunk RearPort
  designations).
- A **Wavelength Editor** tab (ROADM nodes only) for live channel reassignment.

## Line ports

`WdmLinePort` records identify which of the device's `RearPort` instances
carry trunk wavelengths and which direction they belong to. **The plugin
does not create them automatically** -- once a Device exists, you must
add one line port per trunk RearPort before the wavelength-path trace
will recognise that side of the device as a trunk.

| Field | Notes |
|-------|-------|
| `wdm_node` | Parent node |
| `rear_port` | FK to `dcim.RearPort` (must belong to the same device) |
| `direction` | `common`, `east`, or `west` |
| `role` | `tx`, `rx`, or `bidi` |

The recipe per hardware class:

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

Add them from **WDM > Line Ports > Add** or via bulk CSV import. The
fields are deterministic per DeviceType, so a single CSV per hardware
model can provision every device of that model.

Constraints prevent two line ports on the same node from sharing a rear
port, and from having the same direction-role pair.

Patch panels do not need line ports; they appear in the trace via their
ordinary cable terminations.

## Bulk operations

The list view provides bulk import and bulk delete. Bulk import accepts a CSV
or YAML payload with `device`, `node_type`, `grid`, and `description`
columns.
