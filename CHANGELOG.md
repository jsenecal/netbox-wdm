# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `max_trace_hops` plugin setting (default 20): the cable-chain walk cap used by wavelength path discovery and circuit trace rendering is now configurable via `PLUGINS_CONFIG`, and hitting the cap logs a warning instead of silently returning an incomplete path. ([#43](https://github.com/jsenecal/netbox-wdm/issues/43))
- Save-time cable validation: a `netbox.signals.post_clean` receiver on `dcim.Cable` now rejects role-incompatible WDM trunk terminations (TX-to-TX and RX-to-RX line port pairs) with a `ValidationError`, so the NetBox cable form and REST API refuse the miscable instead of accepting it and flagging the resulting wavelength path invalid after the fact. Multi-terminated cables are paired through the cable profile's connector map, so shuffle and breakout profiles are checked along the fibres they actually carry rather than by termination order; unprofiled cables fall back to index pairing, the same guess the tracer degrades to. Terminations that are not WDM line ports are never inspected. A bare `.save()` in a script still bypasses `clean()`, so the existing detection machinery remains as a backstop. ([#42](https://github.com/jsenecal/netbox-wdm/issues/42))

- Module-scoped WDM overlay: `WdmProfile.module_type`, `WdmChannel.module`, and `WdmLinePort.module` let a `dcim.ModuleType` (rather than only a `DeviceType`) carry a WDM profile, so cassette-style modular chassis get one independent set of channels and line ports per installed module.
- WDM Profile tab on `ModuleType` detail pages, matching the existing DeviceType tab: profile summary, channel plans, and line port plans.
- Full CRUD for `WdmLinePortPlan`: `wdm-line-port-plans` REST route, `wdmlineportplan` detail/edit/delete views, and a Line Port Plans card on the WDM Profile and DeviceType/ModuleType WDM Profile tab pages.
- REST API, filtersets, forms, tables, and views for `WdmProfile.module_type`, `WdmChannel.module`, and `WdmLinePort.module`.
- Sample data: a fifth topology, `modular_chassis_span` (2-cassette hub chassis linked through patch panels to two single-cassette peer chassis), demonstrating the module-scoped overlay end to end.
- `docs/user/modular-chassis.md` -- user guide for modular chassis support (profile on ModuleType, per-module channel/line-port grid, install/remove lifecycle, line port plans).

### Changed

- Path rebuilds and port sync rechecks scheduled by signals are now deduplicated per transaction: each affected node is rebuilt once at commit instead of once per created or changed object. Building a two-node topology dropped from 54 rebuild passes to 26 with the same result, and to 2 once the work shares a single transaction. ([#48](https://github.com/jsenecal/netbox-wdm/issues/48))
- Test and sample-data topology builders run inside a single transaction, so the deduplicated rebuild fires once per node for the whole topology rather than once per object created. Combined with the deduplication above this cut a two-node topology build from 5806 to 3183 queries and 18.6s to 9.4s. ([#48](https://github.com/jsenecal/netbox-wdm/issues/48))

- **Breaking:** raised the minimum supported NetBox version from 4.5.0 to 4.6.6. Upcoming changes rely on profile-aware `link_peers` (NetBox 4.6.0) and the `FrontPortFormMixin._save_m2m` template-mapping `post_save` fix in NetBox 4.6.6 (see the Fixed entry below). ([#38](https://github.com/jsenecal/netbox-wdm/issues/38))
- `WdmLinePort.rear_port` and `WdmWavelengthPathChannel.channel` moved from `PROTECT` to `CASCADE`. Deleting a module, a rear port, or a device now cascades its WDM overlay objects (channels, line ports, wavelength-path entries) instead of raising `ProtectedError`; wavelength paths are derived data, so any path left broken by the cascade is pruned, and affected nodes are automatically retraced and rechecked for port sync.
- Port-sync hash format changed: `expected_port_hash` and the computed actual-port hash now include the module (or `0` for device-level ports) in every hashed tuple so fixed and ROADM port groups are diffed per module instead of pooling all of a device's ports together. Hashes computed under the old format no longer match; after upgrading, run `python manage.py wdm_rehash_ports` once to recompute `expected_port_hash` for existing `WdmNode` rows.
- Strand pairing on multi-terminated (duplex) cables is now resolved through NetBox 4.6+ cable profiles (`Cable.profile` / `link_peers` connector mapping) instead of pairing the Nth A-side termination with the Nth B-side termination by pk order, which silently followed the wrong strand whenever termination rows were recreated out of creation order. The testing and sample-data cable builders now assign `trunk-2c1p` to duplex cables and `single-1c1p` to simplex cables. Unprofiled legacy cables still trace via the old index pairing as an explicit fallback, and each use logs a warning naming the cable; the trace visualisation's silent "first available far-end termination" guess is removed. Assign a cable profile to WDM trunk cables to make strand pairing explicit. ([#39](https://github.com/jsenecal/netbox-wdm/issues/39))

### Fixed

- Wavelength path rebuilds are now scoped to the cable event that triggered them. Deleting a cable rebuilds only the WDM nodes whose cable paths crossed it (found via NetBox's `CablePath` flattened node list, captured before the delete cascades), instead of every node participating in any wavelength path; a dark trunk with no lit client edge matches no `CablePath` and falls back to the previous full rebuild. Creating a cable now walks outward from its pass-through terminations to the nearest WDM line ports, so a mid-span trunk between two patch panels -- which terminates no line port directly -- triggers path discovery immediately instead of waiting for an unrelated signal. ([#40](https://github.com/jsenecal/netbox-wdm/issues/40))
- Creating a FrontPort on a DeviceType no longer crashes with `AttributeError: 'PortTemplateMapping' object has no attribute 'device'`. NetBox's `FrontPortFormMixin._save_m2m` used to send `post_save` with a hardcoded `sender=PortMapping` even when the instance was a `PortTemplateMapping`; that upstream bug is fixed in NetBox 4.6.6, now the minimum supported version. ([#22](https://github.com/jsenecal/netbox-wdm/issues/22))
- `WdmChannelViewSet.trace` no longer picks an arbitrary TX/BIDI line port on a modular chassis or multi-degree ROADM; it now delegates to the same module- and destination-aware port selection the UI trace view already used, instead of a module- and destination-blind `.first()`.
- The ROADM live wavelength editor no longer offers front ports from unrelated modules as MUX/DEMUX candidates. `WdmNode.validate_channel_mapping` also now rejects a proposed mapping that assigns a channel a front port belonging to a different module.
- The plugin's GraphQL schema was never registered with NetBox: `NetBoxWDMConfig` did not set `graphql_schema`, so NetBox's default resource lookup could not resolve the nested `graphql.schema` module, and every `wdm_*` query field (`wdm_profile`, `wdm_node`, `wdm_channel`, etc.) was silently absent from the live schema, with no error. `graphql_schema = "graphql.schema.schema"` is now set explicitly, matching the convention already used by other owned plugins.
- Structural port repair (`apply_sync`) now rebuilds module-level RearPorts and FrontPorts, not just device-level ones, on NetBox 4.6: a FrontPort or RearPort deleted (or never created) on an installed module is recreated from its ModuleType template, with its PortMapping, the same way device-level ports were already repaired. A deleted `WdmLinePort` is likewise recreated from its `WdmLinePortPlan` on the correct module.

### Removed

- The `isinstance` guard in the `PortMapping` signal handler that ignored `PortTemplateMapping` instances. It worked around NetBox `FrontPortFormMixin._save_m2m` sending `post_save` with `sender=PortMapping` for template mappings on NetBox <4.6.6; the minimum supported version floor (4.6.6) now covers this upstream. ([#41](https://github.com/jsenecal/netbox-wdm/issues/41))

## [0.2.2] - 2026-04-28

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
