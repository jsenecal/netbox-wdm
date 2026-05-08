# WDM Profiles

A **WDM profile** is the blueprint that turns a generic NetBox DeviceType into
a WDM-aware DeviceType. It is a one-to-one overlay on `dcim.DeviceType`,
defining grid choice, node type, and fibre topology.

## Why a profile

NetBox's DeviceType already stores port templates and mechanical layout. The
WDM profile adds the optical metadata that NetBox does not model natively:

- Which ITU grid this hardware uses (DWDM 100 GHz, DWDM 50 GHz, or CWDM).
- Whether it is a terminal MUX, an OADM, a ROADM, or an inline amplifier.
- Whether each channel uses a duplex pair (separate MUX/DEMUX fibres) or a
  single bidirectional fibre.
- Which FrontPortTemplate corresponds to each channel's MUX and DEMUX side.

When a device of this DeviceType is later created, the profile's child rows
(channel plans) are used to bulk-create one `WdmChannel` per ITU position on
the resulting `WdmNode`.

## Fields

| Field | Required | Notes |
|-------|----------|-------|
| `device_type` | yes | One-to-one to `dcim.DeviceType` |
| `node_type` | yes | `terminal_mux`, `oadm`, `roadm`, or `amplifier` |
| `grid` | yes | `dwdm_100ghz` (44 ch), `dwdm_50ghz` (88 ch), or `cwdm` (18 ch) |
| `fiber_type` | yes | `duplex` (default) or `single_fiber` |
| `description` | no | Free-form text |

## Channel plans

Each profile owns zero or more `WdmChannelPlan` rows. A channel plan is the
template entry for one ITU channel, with these fields:

| Field | Notes |
|-------|-------|
| `profile` | Parent WDM profile |
| `grid_position` | Integer position in the ITU grid (1-based, see [ITU Channel Plans](itu-grids.md)) |
| `wavelength_nm` | Wavelength for the position; computed for DWDM, fixed for CWDM |
| `label` | Display label, e.g. `C32`, `C32.5`, `CWDM-1310` |
| `mux_front_port_template` | FK to a `dcim.FrontPortTemplate` on the same DeviceType (the MUX side) |
| `demux_front_port_template` | FK to a `dcim.FrontPortTemplate` on the same DeviceType (the DEMUX side); leave empty for single-fibre profiles |

Database constraints prevent the same DeviceType from re-using a wavelength,
grid position, or front port template across multiple channel plans.

## Creating a profile

The values you fill in describe what the hardware actually is, so the
device's data sheet (or a glance at the front panel) is the easiest
reference while you work.

From the NetBox UI:

1. Navigate to **WDM > Profiles > Add**.
2. Pick the DeviceType. A DeviceType can only have one profile.
3. Set `node_type`, `grid`, and `fiber_type` to match the hardware -- a
   terminal MUX is a terminal MUX, a duplex MUX has separate TX/RX
   fibres, and so on.
4. Save. The profile detail page opens with an empty **Channels** tab.
5. Switch to the **Channels** tab and add one row per ITU position the
   hardware carries, pointing at the matching FrontPortTemplate(s).

Profiles also appear on the DeviceType detail page under a **WDM Profile**
tab; this tab is only visible when a profile exists.

## Editing constraints

Once channels exist on a `WdmNode`, the linked profile's channel plans should
be considered fairly stable; the plugin does not currently auto-propagate
template changes onto existing devices.

There are two safe operations:

- Adding new channel plan rows. Existing devices keep their existing channels;
  newly created devices pick up the larger set.
- Editing free-form fields (`description`).

For changes that affect port assignments on already-deployed devices, prefer
to remap on each `WdmNode` individually rather than editing the template.

## Bulk operations

The list view exposes bulk delete and bulk import. Bulk import accepts a CSV
or YAML payload with the `device_type`, `node_type`, `grid`, and `fiber_type`
columns. Channel plan rows must be added separately.

## Where to look in code

- `netbox_wdm/models.py` defines `WdmProfile` and `WdmChannelPlan`.
- `netbox_wdm/signals.py:_device_post_save` is what creates a `WdmNode` when a
  device is added to a DeviceType that has a profile.
- `netbox_wdm/models.py:WdmNode._auto_populate_channels` materialises the
  channel plan rows into concrete `WdmChannel` rows on a new node.
