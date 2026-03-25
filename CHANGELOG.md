# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `WdmChannelTemplate` now has `mux_front_port_template` and `demux_front_port_template` (replaces single `front_port_template`)
- `WavelengthChannel` now has `mux_front_port` and `demux_front_port` (replaces single `front_port`)
- `WdmTrunkPort` unique constraint changed from `(wdm_node, direction)` to `(wdm_node, direction, role)`
- `validate_channel_mapping()` accepts `{ch_pk: {"mux": id, "demux": id}}` format
- Wavelength editor conditionally shows MUX/DEMUX columns based on fiber type
- Sample data rebuilt with realistic WDM port topologies and end-to-end cabling

### Added

- `WdmDeviceTypeProfile.fiber_type` field (duplex / single_fiber)
- `WdmTrunkPort.role` field (tx / rx / bidi) for duplex trunk port pairs
- WDM Profile tab on DeviceType detail pages via `@register_model_view`
- EXP (express/upgrade) and 1310 pass-through ports in sample data
- Fiber patch panels and profiled trunk cables in sample data
- EDFA amplifier modeled as FrontPort+RearPort pass-through for CablePath tracing
- Daisy-chain topology demo (EXP port to second MUX COM port)

## [0.1.0] - 2025-03-25

### Added

- `WdmDeviceTypeProfile` model  - 1:1 overlay on `dcim.DeviceType` for WDM blueprints
- `WdmChannelTemplate` model  - channel-to-port blueprint on a profile
- `WdmNode` model  - 1:1 overlay on `dcim.Device` for WDM instances
- `WdmTrunkPort` model  - identifies trunk RearPorts with east/west/common direction
- `WavelengthChannel` model  - per-channel instance on a WDM node
- `WavelengthService` model  - end-to-end wavelength service with lifecycle management
- `WavelengthServiceChannelAssignment`  - sequenced M2M through model
- `WavelengthServiceNode`  - PROTECT guard preventing deletion of in-use channels
- ITU grid constants: DWDM 100GHz (44ch), DWDM 50GHz (88ch), CWDM (18ch)
- Auto-population of channels from profile templates on device creation
- Signal-based auto-creation of `WdmNode` when a profiled `DeviceType` is used
- TypeScript wavelength editor with undo/redo, optimistic concurrency, dirty state
- REST API: full CRUD for all models, `apply-mapping` and `stitch` custom actions
- GraphQL: strawberry-django types, filters, and schema for all models
- Full CRUD views: list, detail, edit, delete, bulk import/edit/delete
- WDM component CSS library with dark/light theme support
- CI pipeline: lint, typecheck, matrix testing (Python 3.12/3.13, NetBox 4.5.4/4.5.5)
- PyPI publish workflow on GitHub release
