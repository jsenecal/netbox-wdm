# NetBox WDM

Wavelength Division Multiplexing (WDM) device management for NetBox.

netbox-wdm overlays NetBox's `dcim.DeviceType` and `dcim.Device` models with WDM
specific records: ITU channel plans, channel-to-port assignments, trunk
direction labelling, ROADM live editing, wavelength service tracking, and
interactive circuit trace visualisation.

## What it manages

- **Device-type blueprints** for terminal MUX, OADM, ROADM, and amplifier
  hardware on the DWDM C-band 100 GHz, DWDM C-band 50 GHz, DWDM L-band
  100 GHz, DWDM L-band 50 GHz, and CWDM grids.
- **Channel-to-port assignments** for both duplex (separate MUX/DEMUX fibres)
  and single-fibre topologies.
- **Trunk port identification** with direction (common / east / west) and role
  (TX / RX / bidirectional).
- **ROADM live editing** with optimistic concurrency and a TypeScript editor.
- **End-to-end wavelength paths** auto-discovered through the cable plant,
  including patch panel pass-through and ROADM cross-connects.
- **Wavelength services (circuits)** that group one or more wavelength paths,
  with PROTECT guards on assigned channels.
- **Drift detection (port sync)** when port mappings are edited outside the
  plugin.

## When to use it

This plugin is for operators of optical transport networks who want NetBox to
hold the source of truth for:

- Which channels exist on each MUX or ROADM.
- Which client port maps to which channel on which trunk side.
- Which wavelengths are lit, reserved, or available across a path.
- Which physical cables and intermediate patch panels each wavelength
  traverses.

It is **not** a network management or telemetry tool: it does not poll the
optical hardware, it tracks documented intent.

## Quick links

User Guide:

- [Getting Started](user/getting-started.md)
- [DeviceType Setup](user/device-types.md)
- [WDM Profiles](user/wdm-profiles.md)
- [WDM Nodes](user/wdm-nodes.md)
- [ITU Channel Plans](user/itu-grids.md)
- [Cabling and Topologies](user/cabling.md)
- [Wavelength Editor (ROADM)](user/wavelength-editor.md)
- [Wavelength Paths and Circuits](user/circuits.md)
- [Circuit Trace Visualisation](user/circuit-trace.md)
- [Port Sync](user/port-sync.md)

Developer:

- [Architecture](developer/architecture.md)
- [Models Reference](developer/models.md)
- [Port Topology](developer/port-topology.md)
- [Wavelength Path Tracing](developer/path-tracing.md)
- [REST API](developer/rest-api.md)
- [GraphQL API](developer/graphql.md)
- [Port Sync (internal)](developer/port-sync.md)
- [Style Guide](developer/style-guide.md)

External:

- [PyPI package](https://pypi.org/project/netbox-wdm/)
- [GitHub repository](https://github.com/jsenecal/netbox-wdm)
- [Issue tracker](https://github.com/jsenecal/netbox-wdm/issues)

## Status

netbox-wdm is alpha software. The data model and REST API may change between
0.x releases. The plugin requires NetBox 4.6.6 or later, and supports the 4.6
and 4.7 series.
