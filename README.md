# netbox-wdm

[![CI](https://github.com/jsenecal/netbox-wdm/actions/workflows/ci.yml/badge.svg)](https://github.com/jsenecal/netbox-wdm/actions/workflows/ci.yml)
![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)
![NetBox: 4.5+](https://img.shields.io/badge/netbox-4.5%2B-blue)
![Python: 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green)

A [NetBox](https://github.com/netbox-community/netbox) 4.5+ plugin for WDM (Wavelength Division Multiplexing) device management.

Manages ITU channel plans, channel-to-port assignments, trunk port identification, ROADM live editing, and wavelength service tracking.

> **Alpha software.** The API and data model may change between releases. Use in production at your own risk.

## Features

- **Overlay pattern** - `WdmDeviceTypeProfile` overlays `DeviceType` (blueprint), `WdmNode` overlays `Device` (instance)
- **Dual port support** - separate MUX and DEMUX front port assignments per channel, with duplex and single-fiber modes
- **ITU grid support** - DWDM 100GHz (44ch), DWDM 50GHz (88ch), CWDM (18ch)
- **EXP/1310 ports** - express upgrade and 1310nm gray optic pass-through as COM rear port positions
- **Auto-population** - channels automatically created from profile templates when a device is added
- **DeviceType integration** - WDM Profile tab on DeviceType detail pages
- **Wavelength editor** - TypeScript frontend with undo/redo, dirty state, optimistic concurrency, conditional MUX/DEMUX columns
- **Wavelength services** - end-to-end service tracking with sequenced channel assignments and PROTECT guards
- **Full CRUD stack** - list, detail, edit, delete, bulk import/edit/delete views for all models
- **REST API** - CRUD endpoints plus `apply-mapping` (atomic ROADM editor) and `stitch` (wavelength path)
- **GraphQL** - strawberry-django types, filters, and schema for all models
- **Sample data** - management command with realistic WDM topologies, patch panels, and end-to-end cabling

## Requirements

- NetBox 4.5+
- Python 3.12+

## Installation

```bash
pip install netbox-wdm
```

Add to your NetBox configuration:

```python
PLUGINS = ["netbox_wdm"]
```

Then apply migrations:

```bash
cd /opt/netbox/netbox
python manage.py migrate
```

## Development

This project uses a Docker devcontainer for development. See `.devcontainer/` for setup.

```bash
# Lint
ruff check netbox_wdm/
ruff format netbox_wdm/

# Run tests
cd /opt/netbox/netbox
DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v

# Build TypeScript
cd netbox_wdm/static/netbox_wdm
npm install
npm run build
```

## Models

| Model | Description |
|-------|-------------|
| `WdmDeviceTypeProfile` | 1:1 overlay on `dcim.DeviceType` - defines grid, node type, and fiber type (duplex/single_fiber) |
| `WdmChannelTemplate` | Channel-to-port blueprint with MUX and DEMUX front port template assignments |
| `WdmNode` | 1:1 overlay on `dcim.Device` - instance of a WDM device |
| `WdmTrunkPort` | Identifies trunk RearPorts with direction (common/east/west) and role (tx/rx/bidi) |
| `WavelengthChannel` | Per-channel instance with MUX and DEMUX front port assignments |
| `WavelengthService` | End-to-end wavelength service spanning channels |
| `WavelengthServiceChannelAssignment` | Sequenced M2M through model |
| `WavelengthServiceNode` | PROTECT guard preventing deletion of in-use channels |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

AGPL-3.0-or-later - see [LICENSE](LICENSE) for the full text.
