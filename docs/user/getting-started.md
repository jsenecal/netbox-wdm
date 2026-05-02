# Getting Started

This page walks through installing the plugin, creating a first WDM profile on
an existing DeviceType, and verifying that channels are auto-populated when a
device of that type is created.

## Requirements

- NetBox 4.5 or later
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

Apply migrations and collect static files:

```bash
cd /opt/netbox/netbox
python manage.py migrate
python manage.py collectstatic --no-input
```

Restart NetBox (gunicorn, granian, or your service of choice). The plugin
registers a top-level **WDM** menu with sub-items for Profiles, Nodes,
Channels, and Circuits.

## Optional: load sample data

For a working demo topology, run the sample data management command. This
creates a manufacturer, four DeviceTypes (CWDM duplex, CWDM single-fibre,
DWDM 100 GHz, ROADM 2-degree), four topologies (two MUX pairs, MUX-to-ROADM,
and a MUX-ROADM-MUX pass-through), and a handful of circuits.

```bash
python manage.py create_wdm_sample_data
```

To remove and recreate the sample data:

```bash
python manage.py create_wdm_sample_data --flush
```

All sample objects are tagged `wdm-sample-data`, which is what `--flush` keys
off.

## Your first profile and node

The recommended workflow is **profile first, device second**.

### 1. Create a DeviceType with the right port templates

In NetBox, create or pick a DeviceType for your WDM hardware. It must already
have FrontPortTemplate, RearPortTemplate, and PortTemplateMapping records that
match real hardware. For a CWDM 18-channel duplex MUX you typically need:

- 18 FrontPortTemplates `CH1-MUX` ... `CH18-MUX`
- 18 FrontPortTemplates `CH1-DEMUX` ... `CH18-DEMUX`
- Two RearPortTemplates `COM-TX` and `COM-RX` with 18 positions each (plus
  positions for any EXP / 1310 pass-through ports)
- PortTemplateMappings linking each front port template to the matching COM
  rear port at the channel's grid position

For a single-fibre MUX you have one set of 18 `CH{n}` front ports and a single
`COM` rear port.

The plugin does not currently auto-generate port templates; see
[Architecture](../developer/architecture.md) for context on how port templates
are consumed.

### 2. Create a WDM profile on the DeviceType

Navigate to **WDM > Profiles > Add**. Set:

- **Device type:** the DeviceType you just prepared.
- **Node type:** Terminal MUX, OADM, ROADM, or Amplifier.
- **Grid:** DWDM 100 GHz, DWDM 50 GHz, or CWDM.
- **Fiber type:** Duplex or Single Fiber.

Save. A "WDM Profile" tab now appears on the DeviceType detail page.

### 3. Define channel plans

On the WDM profile detail page, switch to the **Channels** tab and add one
**Channel Plan** row per ITU channel. For each row pick the matching
`mux_front_port_template` (and `demux_front_port_template` for duplex
profiles).

The grid_position determines the COM rear port position used for that channel
in PortMappings. See [ITU Channel Plans](itu-grids.md) for the position-to-
wavelength tables.

### 4. Create a Device

When a `dcim.Device` is created with this DeviceType, the plugin signal
`_device_post_save` schedules a `WdmNode` to be created on transaction
commit, copying `node_type` and `grid` from the profile.

When the WdmNode is saved, `_auto_populate_channels()` fires: it iterates the
profile's channel plans, looks up the matching FrontPort instances on the new
device by name, and bulk-creates one `WdmChannel` per plan row with the
`mux_front_port` and `demux_front_port` foreign keys filled in.

Verify by opening the device's WDM Node detail page (linked from the Device
detail page) and checking that the **Channels** tab lists every plan row.

## Next steps

- For a ROADM you can now use the [Wavelength Editor](wavelength-editor.md) to
  assign client ports to channels.
- Cable the device's `LINE-*` rear ports to other WDM devices (directly or
  through patch panels) and the plugin will auto-discover
  [wavelength paths](circuits.md).
- Group paths into circuits to track end-to-end services.
