# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Canonical normalize-toolkit CI/CD shape: 5 GHA workflows (`ci.yml`, `publish.yml`, `docs.yml`, `release-drafter.yml`, `pr-title.yml`) + `.github/release-drafter.yml`.
- `.pre-commit-config.yaml` with ruff hooks + standard pre-commit-hooks + a `commit-msg` stage that rejects AI/Claude attribution lines.
- `.git-template/hooks/commit-msg` (canonical hook tracked in-tree, referenced by pre-commit).
- `docs/zensical.toml` + `docs/index.md` -- documentation site auto-deployed to GitHub Pages on push to `main`.
- `uv.lock` committed for reproducible CI/dev environments.

### Changed

- CI: switched dependency installation to `uv` for faster caching; activates the workspace `.venv` via `GITHUB_PATH` so plain `python` works from `/opt/netbox/netbox`. Codecov upload uses OIDC (tokenless). Existing `test-ts` job and `dist/` up-to-date check preserved.
- `publish.yml` split into `build` (unprivileged) + `publish-to-pypi` (`environment: pypi` with `id-token: write`).
- `pyproject.toml`: added `[docs]` extra (`zensical`); `extend-exclude = ["**/migrations/*.py"]`; ignore `N806` globally (Django `User = get_user_model()` idiom); explicit `[tool.ruff.format]`; bumpver `CHANGELOG.md` file pattern so the Unreleased section is promoted on every version bump.
- README aligned to canonical skeleton (PyPI / Python / NetBox / CI / codecov badges, Compatibility table, Documentation links, Contributing section).

## [0.2.1] - 2026-04-01

### Fixed

- Single-fiber MUX channel highlight now extends to far-end port (falls back to `dst.mux_port` when `demux_port` is absent)
- Reverse internal link (COM -> mux_port) created for bidi ports so far-end channel lights up on hover
- Auto-populate workaround added to `create_sf_mux` and `create_roadm` for `transaction=True` test mode

## [0.2.0] - 2026-04-01

### Added

- **Circuit trace visualization** - interactive horizontal flow diagram on WdmCircuit detail pages, inspired by NetBox's cable trace
  - Devices as NetBox-style boxes with teal (WDM) / purple (PP) headers
  - Cables fan in/out through a central badge (hourglass pattern) with NetBox cable colors
  - Channel front ports (MUX/DEMUX) shown on client-facing side of WDM devices
  - Internal routing as interactive dashed bezier curves (PortMapping, channel-to-COM, ROADM pass-through)
  - Per-wavelength-path hover highlighting with dimming of unrelated elements
  - Shared ports (COM, PP) highlight all paths passing through them
  - Port outlines tinted with cable color (port color > cable color > default)
  - Zoom, pan, and fit-to-view controls
- **Channel trace view** - single-channel vertical trace diagram on WdmChannel detail pages
- **Wavelength path model** - `WdmWavelengthPath` tracks end-to-end traced paths between WDM nodes
  - `WdmWavelengthPathChannel` M2M through model for sequenced channel assignments
  - Bidirectional path tracing (A-to-B and B-to-A) for duplex topologies
  - `is_valid` flag to detect TX-to-TX cabling errors
- **WDM circuit model** - `WdmCircuit` groups one or more wavelength paths into a logical service
  - M2M relationship to wavelength paths
  - Circuit detail page with trace tab
- **ROADM pass-through tracing** - wavelength paths correctly traverse multi-degree ROADM nodes
  - `trace_wavelength_path()` tries all TX ports, preferring unvisited destinations
  - `_find_origin()` tries all RX ports on multi-degree nodes
  - Cross-segment internal link detection (LINE-EAST-RX to LINE-WEST-TX)
- **Duplex cabling** - `cable_duplex_through_pp_pair()` creates 3 multi-terminated cables instead of 6 simplex
  - Position-index matching via `cable_end` A/B for correct fibre following
  - Directed trace segments with `to_node` parameter for multi-TX port selection
- **Port sync validation** - detect and fix port drift between DeviceType templates and device instances
  - `expected_port_hash` and `port_sync_valid` fields on WdmNode
  - Port sync diff computation and `apply_sync` with dry_run support
  - `sync-ports` API endpoint, `wdm_sync_ports` management command
  - Warning banner on out-of-sync devices with AJAX "Sync Now" button
  - Split validation by node type (fixed vs ROADM)
  - `wdm_rehash_ports` command for computing missing hashes
- **Testing topology builders** in `netbox_wdm.testing` package
  - `duplex_mux_pair()`, `sf_mux_pair()`, `dwdm_mux_to_roadm()`, `mux_roadm_mux()`
  - Shared DCIM factories, device type factories, device builders, and cabling helpers
  - Conftest fixtures for all device types
- **CI: TypeScript build + stale dist check** - verifies committed dist/ files match source

### Changed

- `WdmChannelTemplate` now has `mux_front_port_template` and `demux_front_port_template` (replaces single `front_port_template`)
- `WdmChannel` (was `WavelengthChannel`) now has `mux_front_port` and `demux_front_port` (replaces single `front_port`)
- `WdmLinePort` (was `WdmTrunkPort`) unique constraint changed from `(wdm_node, direction)` to `(wdm_node, direction, role)`
- `validate_channel_mapping()` accepts `{ch_pk: {"mux": id, "demux": id}}` format
- Wavelength editor conditionally shows MUX/DEMUX columns based on fiber type
- Channel label and wavelength_nm derived from grid constants (no longer stored separately)
- Wavelength values use `Decimal` throughout instead of `float`
- Sample data rebuilt with realistic WDM port topologies, duplex cabling, and cable colors
- Test suite rewritten to use shared topology builders with PP pair topologies

### Fixed

- Trace through intermediate devices (patch panels, EDFAs) via multi-termination cables
- Computed label/wavelength columns now sortable via `grid_position`

## [0.1.0] - 2025-03-25

### Added

- `WdmDeviceTypeProfile` model - 1:1 overlay on `dcim.DeviceType` for WDM blueprints
- `WdmChannelTemplate` model - channel-to-port blueprint on a profile
- `WdmNode` model - 1:1 overlay on `dcim.Device` for WDM instances
- `WdmTrunkPort` model - identifies trunk RearPorts with east/west/common direction
- `WavelengthChannel` model - per-channel instance on a WDM node
- `WavelengthService` model - end-to-end wavelength service with lifecycle management
- `WavelengthServiceChannelAssignment` - sequenced M2M through model
- `WavelengthServiceNode` - PROTECT guard preventing deletion of in-use channels
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
