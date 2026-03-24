# netbox-wdm Implementation Status

**Date:** 2026-03-24

## What Was Built

A standalone NetBox 4.5+ plugin for WDM device management, extracted from netbox-fms.

### Models (8 total)
- `WdmDeviceTypeProfile` — 1:1 overlay on `dcim.DeviceType` (blueprint)
- `WdmChannelTemplate` — channel-to-port blueprint on profile
- `WdmNode` — 1:1 overlay on `dcim.Device` (instance), auto-populates channels from profile
- `WdmTrunkPort` — identifies trunk RearPorts (east/west/common)
- `WavelengthChannel` — per-channel instance on a WDM node
- `WavelengthService` — end-to-end wavelength service (extracted from netbox-fms without FiberCircuit FK)
- `WavelengthServiceChannelAssignment` — sequenced M2M through model
- `WavelengthServiceNode` — PROTECT guard preventing deletion of in-use channels

### Full CRUD Stack
- Forms, filter forms, import forms, bulk edit forms
- FilterSets with `SearchFieldsMixin` (defined locally — not in NetBox core)
- Tables with linkify, toggle, actions columns
- Views: list, detail, edit, delete, bulk import/edit/delete, child tabs
- URL routing via `get_model_urls()` for registered model views

### REST API
- 6 ViewSets (profiles, channel-templates, nodes, trunk-ports, channels, services)
- `POST /api/plugins/wdm/wdm-nodes/{pk}/apply-mapping/` — atomic ROADM channel editor
- `GET /api/plugins/wdm/wavelength-services/{pk}/stitch/` — stitched wavelength path
- Validation inside `transaction.atomic()`, returns `last_updated` for optimistic concurrency

### GraphQL
- strawberry-django types for all 6 main models with lazy forward references
- Filter classes for profile, node, channel, service
- Schema with single + list queries

### TypeScript Wavelength Editor
- `WavelengthEditor` class with undo/redo stack, dirty state detection
- Port assignment dropdowns for available channels, lock icon for reserved/lit
- Ctrl+Z / Ctrl+Shift+Z keyboard shortcuts, beforeunload guard
- Save with 200/400/409 handling, conflict reload prompt

### Infrastructure
- Signal handler: auto-creates `WdmNode` when Device is created from a WDM-profiled DeviceType
- Search indexes for WdmNode, WavelengthChannel, WavelengthService
- Navigation menu (WDM group with 4 items)
- Template extension: WDM panel on Device detail page
- DevContainer configuration (docker-compose, Dockerfile, env files)
- CI/CD: GitHub Actions for lint + test matrix + PyPI publish

## What Remains (Requires DevContainer)

### 1. Generate initial migration
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_wdm
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

### 2. Build TypeScript
```bash
cd /opt/netbox-wdm/netbox_wdm/static/netbox_wdm
npm install
npm run build
```
This produces `dist/wavelength-editor.min.js` and `.map`.

### 3. Run test suite
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```
Tests exist for: constants, models (creation, constraints, auto-populate, validation), API (CRUD, apply-mapping, stitch), GraphQL (import smoke tests).

### 4. Verify plugin loads
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c \
  "import django; django.setup(); from netbox_wdm.models import *; from netbox_wdm.forms import *; from netbox_wdm.filters import *; print('OK')"
```

### 5. TypeScript typecheck
```bash
cd /opt/netbox-wdm/netbox_wdm/static/netbox_wdm
npx tsc --noEmit
```

### 6. Fix any test failures
Tests were written without being run. Expect potential issues with:
- Import paths that may need adjustment once NetBox is in the environment
- Test fixtures that may need additional required fields (e.g., Site, Manufacturer)
- API test authentication setup (NetBox API tests typically need `self.client.force_login()`)

## Key Design Decisions

- **WavelengthService included** despite spec saying "No WavelengthService" — user requested extraction without FiberCircuit FK. The `WavelengthServiceCircuit` model was dropped; `WavelengthServiceNode` simplified to channel-only PROTECT guard.
- **SearchFieldsMixin defined locally** in `filters.py` — it's a custom mixin from netbox-fms, not in NetBox core.
- **`_retrace_affected_paths`** uses OR-chained Q objects on CablePath JSONField — may need adjustment based on actual NetBox CablePath internals.

## Reference Files

- **Spec:** `../netbox-fms/docs/superpowers/specs/2026-03-23-netbox-wdm-standalone-plugin.md`
- **Plan:** `docs/superpowers/plans/2026-03-23-netbox-wdm-implementation.md`
- **Existing netbox-fms WDM code:** `../netbox-fms/netbox_fms/models.py` (lines 1570-2129)
