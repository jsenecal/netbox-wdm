# netbox-wdm

> A [NetBox](https://github.com/netbox-community/netbox) 4.6.6+ plugin for WDM (Wavelength Division Multiplexing) device management.

[![PyPI](https://img.shields.io/pypi/v/netbox-wdm.svg)](https://pypi.org/project/netbox-wdm/)
[![Python](https://img.shields.io/pypi/pyversions/netbox-wdm.svg)](https://pypi.org/project/netbox-wdm/)
[![NetBox](https://img.shields.io/badge/NetBox-4.6.6%2B-success.svg)](https://github.com/netbox-community/netbox)
[![CI](https://github.com/jsenecal/netbox-wdm/actions/workflows/ci.yml/badge.svg)](https://github.com/jsenecal/netbox-wdm/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jsenecal/netbox-wdm/branch/main/graph/badge.svg)](https://codecov.io/gh/jsenecal/netbox-wdm)
[![Documentation](https://img.shields.io/badge/docs-jsenecal.github.io-blue)](https://jsenecal.github.io/netbox-wdm/)
![Status](https://img.shields.io/badge/status-alpha-orange)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)

Manages ITU channel plans, channel-to-port assignments, trunk port identification, ROADM live editing, and wavelength service tracking.

> **Alpha software.** The API and data model may change between releases. Use in production at your own risk.

## Features

- **Overlay pattern** -- `WdmDeviceTypeProfile` overlays `DeviceType` (blueprint), `WdmNode` overlays `Device` (instance).
- **Dual port support** -- separate MUX and DEMUX front port assignments per channel, with duplex and single-fiber modes.
- **ITU grid support** -- DWDM 100 GHz (44 ch), DWDM 50 GHz (88 ch), CWDM (18 ch).
- **EXP / 1310 ports** -- express upgrade and 1310 nm gray optic pass-through as COM rear port positions.
- **Auto-population** -- channels automatically created from profile templates when a device is added.
- **DeviceType integration** -- WDM Profile tab on DeviceType detail pages.
- **Modular chassis support** -- a WDM profile can also attach to a `ModuleType`, so a multi-bay chassis gets one independent set of channels and line ports per installed cassette module.
- **Wavelength editor** -- TypeScript frontend with undo/redo, dirty state, optimistic concurrency, conditional MUX/DEMUX columns.
- **Wavelength services** -- end-to-end service tracking with sequenced channel assignments and PROTECT guards.
- **Circuit trace visualization** -- interactive horizontal flow diagram on `WdmCircuit` detail pages.
- **Full CRUD stack** -- list, detail, edit, delete, bulk import/edit/delete views for all models.
- **REST API** -- CRUD endpoints plus `apply-mapping` (atomic ROADM editor) and `stitch` (wavelength path).
- **GraphQL** -- strawberry-django types, filters, and schema for all models.
- **Sample data** -- management command with realistic WDM topologies, patch panels, and end-to-end cabling.

## Compatibility

| Plugin version    | NetBox version | Python    |
|-------------------|----------------|-----------|
| main (unreleased) | 4.6.6+         | 3.12-3.14 |
| 0.2.x             | 4.5            | 3.12-3.14 |

## Installation

```bash
pip install netbox-wdm
```

In your NetBox `configuration.py`:

```python
PLUGINS = ["netbox_wdm"]
```

### Configuration

Optional settings, with their defaults, in `PLUGINS_CONFIG`:

```python
PLUGINS_CONFIG = {
    "netbox_wdm": {
        # Maximum number of hops the cable-chain walker follows between two
        # WDM nodes (path discovery and circuit trace rendering). Raise this
        # if legitimate chains pass through more intermediate devices; a
        # warning is logged when the cap truncates a trace.
        "max_trace_hops": 20,
    },
}
```

Apply migrations:

```bash
cd /opt/netbox/netbox
python manage.py migrate
```

## Documentation

Full documentation: **[jsenecal.github.io/netbox-wdm](https://jsenecal.github.io/netbox-wdm/)**

Key references:
- `docs/developer/architecture` -- overlay pattern, port topology, position-stack alignment.
- `docs/developer/style-guide` -- frontend conventions for the TypeScript components.
- `docs/user/modular-chassis` -- WDM profiles on ModuleType, per-module channels and line ports, install/remove lifecycle.

## Models

| Model | Description |
|-------|-------------|
| `WdmDeviceTypeProfile` | 1:1 overlay on `dcim.DeviceType` -- defines grid, node type, and fiber type (duplex / single-fiber) |
| `WdmChannelTemplate`   | Channel-to-port blueprint with MUX and DEMUX front port template assignments |
| `WdmNode`              | 1:1 overlay on `dcim.Device` -- instance of a WDM device |
| `WdmLinePort`          | Identifies trunk RearPorts with direction (common / east / west) and role (tx / rx / bidi) |
| `WdmChannel`           | Per-channel instance with MUX and DEMUX front port assignments |
| `WdmWavelengthPath`    | End-to-end traced path through the cable plant between WDM nodes |
| `WdmCircuit`           | Logical service grouping one or more wavelength paths |

## Modular chassis support

Some WDM hardware is a bare chassis that takes swappable cassette modules
(for example, a 1RU shelf with two CWDM MUX/DEMUX bays). netbox-wdm models
this by letting a `WdmProfile` attach to a `dcim.ModuleType` instead of a
`DeviceType`: each installed `Module` gets its own `WdmChannel` and
`WdmLinePort` rows, scoped to that module, so two cassettes in the same
chassis behave as independent WDM nodes that happen to share a device shell.
Installing or removing a module creates or tears down its channels and line
ports automatically; wavelength paths and port-sync state are retraced for
any node affected by the change. See `docs/user/modular-chassis` for the
full lifecycle and a worked example.

## Related plugins

netbox-wdm is part of a three-plugin set that models the full optical transport stack:

- **[netbox-fms](https://github.com/jsenecal/netbox-fms)** -- Fiber Management System. Defines fiber cable construction (buffer tubes, ribbons, strands), plans splices in closures, and provisions the fiber circuits that WDM wavelength paths ride on.
- **[netbox-pathways](https://github.com/jsenecal/netbox-pathways)** -- physical cable plant documentation with PostGIS. Models conduits, aerial spans, structures (poles, manholes, cabinets), and the geographic routes the cables carrying WDM circuits traverse.

## Contributing

PRs welcome. Use conventional-commits PR titles (`feat:`, `fix:`, `chore:`, `docs:`, ...) -- release-drafter assembles release notes from them. Run `make setup` after cloning to install dev dependencies and the pre-commit hooks (including the AI-attribution-rejecting `commit-msg` hook).

## License

[AGPL-3.0-or-later](LICENSE).
