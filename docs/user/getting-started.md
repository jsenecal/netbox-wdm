# Getting Started

This page walks through everything required to take an empty NetBox
install to a working WDM topology with auto-discovered wavelength paths.
It mirrors the same sequence the bundled `create_wdm_sample_data`
management command performs internally, with cross-links to the
reference docs for each step.

## Requirements

- NetBox 4.6.6 or later (4.6 and 4.7 series supported)
- Python 3.12, 3.13, or 3.14
- PostgreSQL with PostGIS (the standard NetBox database)

## Install

Install the package from PyPI:

```bash
pip install netbox-wdm
```

Enable the plugin in your NetBox `configuration.py`:

```python
PLUGINS = ["netbox_wdm"]
```

### Plugin settings

All settings are optional; defaults are shown below.

```python
PLUGINS_CONFIG = {
    "netbox_wdm": {
        "max_trace_hops": 100,
    },
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `max_trace_hops` | `100` | Maximum number of cable segments the chain walker follows between two WDM nodes. Both wavelength path discovery and circuit trace rendering stop after this many segments, alongside a loop check that refuses any chain revisiting a port. Raise it if legitimate chains pass through more intermediate devices (patch panels, amplifiers, carrier circuits); when the cap or the loop check stops a trace, a warning is logged so the incomplete path is visible. |

Apply migrations and collect static files:

```bash
cd /opt/netbox/netbox
python manage.py migrate
python manage.py collectstatic --no-input
```

Restart NetBox. The plugin registers a top-level **WDM** menu with
sub-items for Profiles, Channel Plans, Nodes, Line Ports, Channels,
Wavelength Paths, and Circuits.

## Optional: load sample data

For a working demo topology you can inspect before building your own:

```bash
python manage.py create_wdm_sample_data
python manage.py create_wdm_sample_data --flush   # remove and recreate
```

This populates a single site with four cabled topologies (CWDM duplex,
CWDM single-fibre, DWDM-to-ROADM, and a MUX-ROADM-MUX pass-through), a
matrix of channel statuses, and a handful of circuits. Everything it
creates is tagged `wdm-sample-data` so `--flush` can clean up.

The sample data is a useful read-only reference; you can skip it on a
production install.

## The setup chain

Real provisioning happens in this order. Each step has a dedicated page
linked below; follow them top to bottom for your first WDM site.

### 1. Lay out the DeviceType boilerplate

netbox-wdm does not auto-generate port templates. Before you create a
WDM profile, the underlying NetBox DeviceType must already have:

- FrontPortTemplates for every per-channel client port plus any
  pass-through ports (EXP, 1310).
- RearPortTemplates for the trunk side, with `positions` covering every
  channel and pass-through.
- PortTemplateMappings linking each FrontPortTemplate to the right
  RearPortTemplate at the right `rear_port_position`.

**The single rule that ties everything together:** every PortTemplateMapping's
`rear_port_position` must equal the `grid_position` of the channel it
carries.

The recipes for duplex MUX, single-fibre MUX, ROADM, EDFA, and patch
panel hardware are listed in [DeviceType Setup](device-types.md).

### 2. Create a WDM profile on the DeviceType

The [WDM profile](wdm-profiles.md) is the optical metadata layer.
Each field describes what the hardware is, so the device's data sheet
or front-panel labelling is the easiest reference:

- `node_type`: `terminal_mux`, `oadm`, `roadm`, or `amplifier`.
- `grid`: `dwdm_c_100ghz`, `dwdm_c_50ghz`, `dwdm_l_100ghz`, `dwdm_l_50ghz`, or
  `cwdm` (see [ITU Channel Plans](itu-grids.md) for which labels match
  which grid).
- `fiber_type`: `duplex` if the device exposes separate MUX and DEMUX
  front ports per channel, `single_fiber` if it uses one bidirectional
  port per channel.

Create it from **WDM > Profiles > Add**, picking the DeviceType. A
DeviceType can have at most one profile, so there is a 1:1 relationship.
A "WDM Profile" tab appears on the DeviceType detail page once the
profile exists.

### 3. Add channel plans to the profile

For every ITU position the hardware carries, add one
`WdmChannelPlan` row from the **Channels** tab on the profile detail
page. Each row binds:

- `grid_position` (the integer index in the grid; see
  [ITU Channel Plans](itu-grids.md))
- `mux_front_port_template` (the channel's MUX FrontPortTemplate)
- `demux_front_port_template` (the DEMUX FrontPortTemplate, **null** for
  single-fibre profiles)

The plugin auto-fills `wavelength_nm` and `label` from the chosen grid
position.

### 4. Create Devices

Create `dcim.Device` instances of the DeviceType. As each Device is
saved, a `post_save` signal schedules a [WDM node](wdm-nodes.md) to be
created on transaction commit, copying `node_type` and `grid` from the
profile. When the WdmNode saves, `_auto_populate_channels()` runs:

1. Loads every `WdmChannelPlan` row on the profile.
2. Looks up matching `FrontPort` instances on the new Device by name.
3. Bulk-creates one `WdmChannel` per plan with its MUX/DEMUX FrontPort
   FKs filled in.

Amplifier nodes skip channel auto-population because amplifiers do not
carry per-channel client ports.

### 5. Add line ports

`WdmLinePort` rows tag the device's trunk RearPorts with a direction
and role. They are **not** auto-created -- you must add them per device
from **WDM > Line Ports > Add** or via bulk CSV import. The recipe
table for each hardware class is in
[Creating line ports](device-types.md#creating-line-ports).

A duplex MUX gets two line ports (`(common, tx)` and `(common, rx)`).
A single-fibre MUX gets one (`(common, bidi)`). A 2-degree ROADM gets
four (one per direction-role pair).

### 6. Cable the trunk side

Wire the device's trunk RearPorts (or the line ports' rear ports) to
other WDM devices, directly or through patch panels. Use the cabling
patterns in [Cabling and Topologies](cabling.md):

- Single-fibre links use one termination per cable.
- Duplex links use multi-terminated cables (both fibres on a single
  `dcim.Cable`).
- ROADM line ports connect to MUX `COM-TX/RX` with a TX/RX flip on the
  far side.

When cables are saved, signal handlers rebuild any affected wavelength
paths automatically.

### 7. Verify wavelength paths

Open **WDM > Wavelength Paths**. Each path lists:

- Its grid position and wavelength.
- `is_complete` (both endpoints have client ports assigned).
- `is_active` (every cable along the path is `connected`).
- `is_valid` (no TX-to-TX miscable).

If your trace shows zero paths after cabling, the most common causes
are missing line ports (step 5), missing PortTemplateMappings (step 1),
or duplex cables wired without the TX/RX flip on the far side. See
[Cabling validity checks](cabling.md#validity-checks).

### 8. (Optional) Set channel statuses

Channels start as `available`. Move them to `reserved` once a
wavelength is committed but not yet turned up, and to `active` once
service is live. The [Wavelength Editor](wavelength-editor.md) and the
`apply-mapping` API refuse to remap channels in `reserved` or
`active` status; this is the PROTECT guard that prevents accidental
reassignment of a channel under a live service.

### 9. (Optional) Group paths into circuits

A [WDM circuit](circuits.md) is a logical service over one or more
wavelength paths. Typical patterns:

- A bidirectional service attaches **both** directional paths (A-to-B
  and B-to-A) for a single wavelength.
- A bonded service attaches both directions of multiple wavelengths.
- A pass-through service attaches paths that traverse a ROADM.

Decommissioning a circuit clears its M2M and resets every channel on
every attached path back to `available`.

## What the plugin auto-creates vs what you create manually

| Object | Created by |
|--------|------------|
| FrontPortTemplate, RearPortTemplate, PortTemplateMapping | You, on the DeviceType |
| WdmProfile | You, once per DeviceType |
| WdmChannelPlan | You, one per ITU position on the profile |
| Device | You, normal NetBox flow |
| FrontPort, RearPort | NetBox, when the Device is saved (from templates) |
| WdmNode | Plugin signal, on Device save |
| WdmChannel | Plugin (`_auto_populate_channels`), on WdmNode save |
| dcim.PortMapping | NetBox (from PortTemplateMapping) and the plugin (on `apply-mapping` for ROADMs) |
| WdmLinePort | You, one per trunk RearPort per device |
| Cable | You |
| WdmWavelengthPath, WdmWavelengthPathChannel | Plugin signals, on cable or channel changes |
| WdmCircuit | You, when grouping paths into a service |

If something further down the chain is missing, check the row above it in
the table. The most common "nothing is happening" cause is a missing
WdmLinePort, since the trace cannot identify which RearPorts are trunks
without it.

## Next steps

- [DeviceType Setup](device-types.md) for the per-hardware recipes.
- [WDM Profiles](wdm-profiles.md) and
  [WDM Nodes](wdm-nodes.md) for the model-by-model reference.
- [Cabling and Topologies](cabling.md) for the patterns the trace
  follows.
- [Wavelength Editor](wavelength-editor.md) for ROADM live channel
  reassignment.
- [Circuits](circuits.md) and
  [Circuit Trace Visualisation](circuit-trace.md) for service tracking.
- [Port Sync](port-sync.md) when port mappings drift outside the
  plugin.
