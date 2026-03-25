# WDM DeviceType Integration - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the WDM models to support real-world MUX/DEMUX port pairs with EXP/1310 pass-through, add a DeviceType tab for WDM profile visibility, and rebuild sample data with realistic hardware topologies and full end-to-end cabling.

**Architecture:** Real WDM hardware has separate MUX and DEMUX client front ports per wavelength, with all signals multiplexed through COM rear port(s) at specific positions. EXP (express/upgrade) and 1310 pass-through are additional front port pairs that occupy their own positions on the same COM rear ports. EDFAs use FrontPort+RearPort with PortMapping for CablePath pass-through. `WdmTrunkPort` gains a `role` field (tx/rx/bidi) for duplex trunk pairs. Single-fiber devices use one COM port with bidi role.

**Approach:** Delete all existing migrations and start from a fresh `0001_initial`. Wipe the dev database and devcontainer data.

**Tech Stack:** Django 5.x, NetBox 4.5+, Python 3.12+, TypeScript (esbuild)

**Deferred:** ROADM multi-channel-per-port, OADM node type, port template auto-gen wizard, red/blue band - see `docs/TODO.md`.

---

## Port Topology Reference

### Duplex Fiber MUX/DEMUX (most common)
```
FRONT (client-facing):
  CH{n}-MUX, CH{n}-DEMUX     per channel (e.g., 8x2 = 16 ports)
  EXP-MUX, EXP-DEMUX         express/upgrade (carries unfiltered wavelengths)
  1310-MUX, 1310-DEMUX        gray optic pass-through

REAR (line-facing):
  COM-TX  (positions = channels + EXP + 1310)
  COM-RX  (positions = channels + EXP + 1310)

PortMappings:
  CH1-MUX     -> COM-TX pos 1     |  CH1-DEMUX     -> COM-RX pos 1
  CH2-MUX     -> COM-TX pos 2     |  CH2-DEMUX     -> COM-RX pos 2
  ...                              |  ...
  EXP-MUX     -> COM-TX pos N+1   |  EXP-DEMUX     -> COM-RX pos N+1
  1310-MUX    -> COM-TX pos N+2   |  1310-DEMUX    -> COM-RX pos N+2
```

### Single Fiber MUX (BiDi)
```
FRONT: CH{n} per channel (bidirectional), EXP, 1310
REAR:  COM (single port, positions = channels + EXP + 1310)
```

### ROADM (Duplex) - simplified for now
```
FRONT: ADD-{n}, DROP-{n}  per add/drop port
REAR:  LINE-EAST-TX, LINE-EAST-RX, LINE-WEST-TX, LINE-WEST-RX
```

### Amplifier (EDFA) - FrontPort + RearPort for CablePath tracing
```
FRONT: LINE-IN  (FrontPort, signal input)
REAR:  LINE-OUT (RearPort, amplified output)
PortMapping: LINE-IN -> LINE-OUT (pass-through)
```

### End-to-End Cabling Example
```
[Router IF] --patch--> [MUX CH1-MUX FP]
  PortMapping: CH1-MUX FP -> COM-TX RP pos 1
[COM-TX RP] --profiled trunk cable pos 1--> [Patch Panel RP]
  PortMapping: PP RP pos 1 -> PP FP1
[PP FP1] --patch--> [Remote PP FP1]
  PortMapping: Remote PP FP1 -> Remote PP RP pos 1
[Remote PP RP] --profiled trunk cable pos 1--> [Remote MUX COM-RX RP]
  PortMapping: COM-RX RP pos 1 -> CH1-DEMUX FP
[Remote MUX CH1-DEMUX FP] --patch--> [Remote Router IF]
```

---

## File Structure

### Modified Files

| File | Responsibility |
|------|----------------|
| `netbox_wdm/models.py` | Rename `front_port_template`->`mux_front_port_template`, add `demux_front_port_template`; rename `front_port`->`mux_front_port`, add `demux_front_port`; add `fiber_type` to profile; add `role` to WdmTrunkPort |
| `netbox_wdm/choices.py` | Add `WdmFiberTypeChoices`, `WdmTrunkRoleChoices` |
| `netbox_wdm/forms.py` | Update all forms for renamed/new fields |
| `netbox_wdm/filters.py` | Add `fiber_type` filter |
| `netbox_wdm/tables.py` | Update column names |
| `netbox_wdm/api/serializers.py` | Update field names |
| `netbox_wdm/api/views.py` | Update `_apply_mapping` for dual ports |
| `netbox_wdm/views.py` | Update `select_related`, add DeviceType tab, update editor context |
| `netbox_wdm/templates/netbox_wdm/*.html` | Update field references in all detail templates |
| `netbox_wdm/static/netbox_wdm/src/wavelength-editor*.ts` | Dual port columns, conditional DEMUX column based on fiberType |
| `netbox_wdm/management/commands/create_wdm_sample_data.py` | Full rewrite with realistic topologies and end-to-end cabling |
| `tests/test_models.py` | Update for renamed fields, add dual-port and fiber_type tests |
| `tests/test_api.py` | Update for renamed fields |

### New Files

| File | Responsibility |
|------|----------------|
| `netbox_wdm/templates/netbox_wdm/devicetype_wdm_tab.html` | DeviceType WDM profile tab template |

### Deleted Files

| File | Reason |
|------|--------|
| `netbox_wdm/migrations/0001_initial.py` | Fresh migration from scratch |
| `netbox_wdm/migrations/0002_*.py` | Fresh migration from scratch |

### Recreated Files

| File | Responsibility |
|------|----------------|
| `netbox_wdm/migrations/0001_initial.py` | Fresh initial migration with all new fields |

---

## Task Breakdown

### Task 0: Clean slate - delete migrations and wipe database

- [ ] **Step 1: Delete all existing migrations**

```bash
rm netbox_wdm/migrations/0001_initial.py netbox_wdm/migrations/0002_*.py
```

- [ ] **Step 2: Wipe the dev database**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py flush --no-input
```

- [ ] **Step 3: Verify clean state**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py showmigrations netbox_wdm
```

Should show no migrations.

---

### Task 1: Model changes, fresh migration, and test fixes

**Files:**
- Modify: `netbox_wdm/choices.py`
- Modify: `netbox_wdm/models.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_api.py`
- Create: `netbox_wdm/migrations/0001_initial.py`

- [ ] **Step 1: Add new choices to choices.py**

Use plain strings (matching existing convention):

```python
class WdmFiberTypeChoices(ChoiceSet):
    DUPLEX = "duplex"
    SINGLE_FIBER = "single_fiber"

    CHOICES = (
        (DUPLEX, "Duplex", "blue"),
        (SINGLE_FIBER, "Single Fiber", "orange"),
    )


class WdmTrunkRoleChoices(ChoiceSet):
    TX = "tx"
    RX = "rx"
    BIDI = "bidi"

    CHOICES = (
        (TX, "TX"),
        (RX, "RX"),
        (BIDI, "Bidirectional"),
    )
```

- [ ] **Step 2: Update WdmDeviceTypeProfile - add fiber_type**

Add field after `grid`, add to `clone_fields`:
```python
fiber_type = models.CharField(
    max_length=50,
    choices=WdmFiberTypeChoices,
    default=WdmFiberTypeChoices.DUPLEX,
    verbose_name=_("fiber type"),
)
```

- [ ] **Step 3: Update WdmChannelTemplate - rename to mux_front_port_template, add demux**

Since we're starting fresh (no migration rename needed), just use the new field names directly:

```python
mux_front_port_template = models.ForeignKey(
    to="dcim.FrontPortTemplate",
    on_delete=models.SET_NULL,
    blank=True,
    null=True,
    related_name="+",
    verbose_name=_("MUX front port template"),
)
demux_front_port_template = models.ForeignKey(
    to="dcim.FrontPortTemplate",
    on_delete=models.SET_NULL,
    blank=True,
    null=True,
    related_name="+",
    verbose_name=_("DEMUX front port template"),
)
```

Update constraint `unique_profile_fpt` to reference `mux_front_port_template`. Add `unique_profile_demux_fpt` for `demux_front_port_template`.

- [ ] **Step 4: Update WavelengthChannel - rename to mux_front_port, add demux_front_port**

Same approach - fresh field names:

```python
mux_front_port = models.ForeignKey(
    to="dcim.FrontPort", on_delete=models.SET_NULL,
    blank=True, null=True, related_name="+",
    verbose_name=_("MUX front port"),
)
demux_front_port = models.ForeignKey(
    to="dcim.FrontPort", on_delete=models.SET_NULL,
    blank=True, null=True, related_name="+",
    verbose_name=_("DEMUX front port"),
)
```

Update constraint `unique_node_fp` -> `unique_node_mux_fp` for `mux_front_port`. Add `unique_node_demux_fp`.

- [ ] **Step 5: Add role field to WdmTrunkPort, update constraint**

```python
role = models.CharField(
    max_length=50,
    choices=WdmTrunkRoleChoices,
    default=WdmTrunkRoleChoices.BIDI,
    verbose_name=_("role"),
)
```

Replace `unique_trunkport_direction` with:
```python
models.UniqueConstraint(
    fields=["wdm_node", "direction", "role"],
    name="unique_trunkport_direction_role",
),
```

- [ ] **Step 6: Update _auto_populate_channels for dual ports**

Update `select_related` to `("mux_front_port_template", "demux_front_port_template")`.
Resolve both template names to actual FrontPort instances on the device.

- [ ] **Step 7: Update validate_channel_mapping for dual ports**

New mapping format: `{ channel_pk: {"mux": port_id|null, "demux": port_id|null} }`

Protected channel check verifies BOTH ports unchanged. Port uniqueness checked independently for mux and demux pools.

- [ ] **Step 8: Generate fresh initial migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_wdm
```

This generates a clean `0001_initial.py` with all fields in their final form - no rename operations needed.

- [ ] **Step 9: Update tests for new field names**

Fix ALL references in `tests/test_models.py` and `tests/test_api.py`:
- `front_port_template` -> `mux_front_port_template`
- `front_port` -> `mux_front_port`
- `front_port_id` -> `mux_front_port_id`

Add tests for `fiber_type` field. Add test for dual-port `_auto_populate_channels()`.

- [ ] **Step 10: Apply migration and run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```

All tests must pass.

- [ ] **Step 11: Commit**

```bash
git add netbox_wdm/models.py netbox_wdm/choices.py netbox_wdm/migrations/ tests/
git commit -m "feat: add dual MUX/DEMUX port support, fiber type, and trunk role"
```

---

### Task 2: Update forms, filters, tables, serializers, and view querysets

**Files:**
- Modify: `netbox_wdm/forms.py`
- Modify: `netbox_wdm/filters.py`
- Modify: `netbox_wdm/tables.py`
- Modify: `netbox_wdm/api/serializers.py`
- Modify: `netbox_wdm/views.py` (select_related updates only)

- [ ] **Step 1: Update forms**

- Profile forms: Add `fiber_type` to fields, fieldsets, import/filter forms
- Channel template form: Replace `front_port_template` with `mux_front_port_template` + `demux_front_port_template`
- Channel form: Replace `front_port` with `mux_front_port` + `demux_front_port`
- Trunk port form: Add `role` field

- [ ] **Step 2: Update filtersets**

Add `fiber_type` MultipleChoiceFilter to `WdmDeviceTypeProfileFilterSet`.

- [ ] **Step 3: Update tables**

All renamed columns + new `fiber_type`, `demux_*`, `role` columns.

- [ ] **Step 4: Update serializers**

All Meta.fields tuples with new field names. Add `fiber_type` to profile, `role` to trunk port.

- [ ] **Step 5: Update select_related in views.py**

Replace all `select_related("front_port")` with `select_related("mux_front_port", "demux_front_port")`.
Replace `select_related("front_port_template")` with `select_related("mux_front_port_template", "demux_front_port_template")`.

- [ ] **Step 6: Run linter and tests**

```bash
ruff check --fix netbox_wdm/ && ruff format netbox_wdm/
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```

- [ ] **Step 7: Commit**

```bash
git add netbox_wdm/forms.py netbox_wdm/filters.py netbox_wdm/tables.py netbox_wdm/api/serializers.py netbox_wdm/views.py
git commit -m "feat: update forms, filters, tables, serializers for dual port support"
```

---

### Task 3: Update API views and wavelength editor for dual ports

**Files:**
- Modify: `netbox_wdm/api/views.py`
- Modify: `netbox_wdm/views.py` (WavelengthEditorView context)
- Modify: `netbox_wdm/static/netbox_wdm/src/wavelength-editor-types.ts`
- Modify: `netbox_wdm/static/netbox_wdm/src/wavelength-editor.ts`

- [ ] **Step 1: Update _apply_mapping for dual ports**

New format: `{ channel_pk: {"mux": port_id|null, "demux": port_id|null} }`

- Track `old_mux_fp_ids` and `old_demux_fp_ids` separately for PortMapping deletion
- Create PortMapping entries for both mux and demux ports
- MUX front ports map to tx-role trunk rear ports; DEMUX front ports map to rx-role trunk rear ports; bidi role trunks get both
- `bulk_update` fields: `["mux_front_port_id", "demux_front_port_id"]`

- [ ] **Step 2: Update WavelengthEditorView get_extra_context**

- Channel data: `mux_front_port_id/name`, `demux_front_port_id/name`
- Available ports: exclude both assigned mux AND demux port IDs
- Add `fiberType` to config from device type's WDM profile

- [ ] **Step 3: Update TypeScript types**

```typescript
export interface ChannelData {
  id: number;
  grid_position: number;
  wavelength_nm: number;
  label: string;
  mux_front_port_id: number | null;
  mux_front_port_name: string | null;
  demux_front_port_id: number | null;
  demux_front_port_name: string | null;
  status: 'available' | 'reserved' | 'lit';
  service_name: string | null;
}

export interface EditorConfig {
  nodeId: number;
  nodeType: string;
  fiberType: 'duplex' | 'single_fiber';
  lastUpdated: string;
  applyUrl: string;
  channels: ChannelData[];
  availablePorts: PortData[];
}
```

- [ ] **Step 4: Update TypeScript editor**

- Duplex: two port columns (MUX Port, DEMUX Port)
- Single fiber: one port column (Port)
- Mapping state: `Map<number, {mux: number|null, demux: number|null}>`
- Undo/redo tracks both old/new mux and demux

- [ ] **Step 5: Rebuild frontend and run tests**

```bash
cd netbox_wdm/static/netbox_wdm && npm run build && npm run typecheck
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add netbox_wdm/api/views.py netbox_wdm/views.py netbox_wdm/static/
git commit -m "feat: update API and wavelength editor for dual MUX/DEMUX ports"
```

---

### Task 4: Update detail templates and add DeviceType tab

Tasks 4 covers all template work including the new DeviceType tab.

**Files:**
- Modify: `netbox_wdm/templates/netbox_wdm/wdmdevicetypeprofile.html`
- Modify: `netbox_wdm/templates/netbox_wdm/wdmchanneltemplate.html`
- Modify: `netbox_wdm/templates/netbox_wdm/wavelengthchannel.html`
- Modify: `netbox_wdm/templates/netbox_wdm/wdmtrunkport.html`
- Modify: `netbox_wdm/views.py` (add DeviceType tab view)
- Create: `netbox_wdm/templates/netbox_wdm/devicetype_wdm_tab.html`

- [ ] **Step 1: Update existing detail templates**

- Profile: Add `fiber_type` row
- Channel template: `mux_front_port_template` + `demux_front_port_template` rows
- Channel: `mux_front_port` + `demux_front_port` rows
- Trunk port: Add `role` row

- [ ] **Step 2: Create DeviceType tab view**

```python
from dcim.models import DeviceType

@register_model_view(DeviceType, "wdm_profile", path="wdm-profile")
class DeviceTypeWdmProfileView(generic.ObjectView):
    queryset = DeviceType.objects.all()
    tab = ViewTab(
        label=_("WDM Profile"),
        badge=lambda obj: WdmDeviceTypeProfile.objects.filter(device_type=obj).exists(),
        permission="netbox_wdm.view_wdmdevicetypeprofile",
        weight=1100,
    )

    def get_template_name(self):
        return "netbox_wdm/devicetype_wdm_tab.html"

    def get_extra_context(self, request, instance):
        profile = WdmDeviceTypeProfile.objects.filter(device_type=instance).first()
        channel_templates = []
        if profile:
            channel_templates = list(
                profile.channel_templates
                .select_related("mux_front_port_template", "demux_front_port_template")
                .order_by("grid_position")
            )
        return {"profile": profile, "channel_templates": channel_templates}
```

- [ ] **Step 3: Create tab template**

Show profile attributes (node type, grid, fiber type, channel count) and channel template table with MUX/DEMUX port columns. Show "No WDM profile" alert when none exists.

- [ ] **Step 4: Commit**

```bash
git add netbox_wdm/views.py netbox_wdm/templates/
git commit -m "feat: update templates and add WDM Profile tab on DeviceType"
```

---

### Task 5: Rebuild sample data with realistic topologies and end-to-end cabling

**Files:**
- Modify: `netbox_wdm/management/commands/create_wdm_sample_data.py`

- [ ] **Step 1: Define device types with correct port topologies**

| DeviceType | Front Ports | Rear Ports | Profile |
|---|---|---|---|
| CWDM-MUX-8-DX | CH1..CH8 MUX+DEMUX (16), EXP-MUX/DEMUX (2), 1310-MUX/DEMUX (2) = 20 | COM-TX (pos=10), COM-RX (pos=10) | duplex, terminal_mux, cwdm |
| CWDM-MUX-8-SF | CH1..CH8 (8), EXP (1), 1310 (1) = 10 | COM (pos=10) | single_fiber, terminal_mux, cwdm |
| DWDM-MUX-44-DX | C21..C64 MUX+DEMUX (88), EXP-MUX/DEMUX (2) = 90 | COM-TX (pos=45), COM-RX (pos=45) | duplex, terminal_mux, dwdm_100ghz |
| EDFA-1RU | LINE-IN (1 FrontPort) | LINE-OUT (1 RearPort) | amplifier, dwdm_100ghz |
| ROADM-2D | ADD-01..20, DROP-01..20 (40) | LINE-EAST-TX/RX, LINE-WEST-TX/RX (pos=44 each) | duplex, roadm, dwdm_100ghz |
| Fiber Patch Panel 24 | FP-01..FP-24 (24 FrontPorts) | RP-01..RP-24 (24 RearPorts, pos=1 each) | N/A (not WDM) |

Note: 8ch CWDM used instead of 18ch to keep sample data manageable while still demonstrating EXP and 1310 ports.

- [ ] **Step 2: Create PortTemplateMappings on DeviceTypes**

For each DeviceType, create the PortTemplateMapping entries linking front port templates to rear port templates at specific positions. This is the blueprint that gets instantiated as PortMappings on Devices.

- [ ] **Step 3: Create channel templates with dual port links**

- Duplex MUX: `mux_front_port_template` = CH{n}-MUX, `demux_front_port_template` = CH{n}-DEMUX
- Single fiber: `mux_front_port_template` = CH{n}, `demux_front_port_template` = null
- ROADM: `mux_front_port_template` = ADD-{n}, `demux_front_port_template` = DROP-{n}

- [ ] **Step 4: Create sites and devices**

3 sites: East POP, West POP, Central Hub. Devices:
- East: CWDM-MUX-8-DX, Fiber Patch Panel
- West: CWDM-MUX-8-DX, Fiber Patch Panel
- Hub: DWDM-MUX-44-DX, ROADM-2D, EDFA-1RU, 2x Fiber Patch Panel
- Also: CWDM-MUX-8-SF at East (single fiber example)

- [ ] **Step 5: Create trunk ports with role**

- Duplex MUX: COM-TX (role=tx, dir=common), COM-RX (role=rx, dir=common)
- Single fiber: COM (role=bidi, dir=common)
- ROADM: LINE-EAST-TX (role=tx, dir=east), LINE-EAST-RX (role=rx, dir=east), etc.

- [ ] **Step 6: Create end-to-end cabling**

Full path: Router -> patch cable -> MUX channel port -> (internal PortMapping) -> COM rear port -> profiled trunk cable -> Patch Panel rear port -> (internal PortMapping) -> Patch Panel front port -> patch cable -> Remote Patch Panel front port -> ... -> Remote MUX -> Remote Router

Create:
- Patch cables: Router interfaces to MUX channel front ports
- Profiled trunk cables: MUX COM rear ports to Patch Panel rear ports (multi-position, cable profile matching channel count)
- Inter-site trunk cables: Patch Panel to Patch Panel (profiled)
- EDFA inline: trunk cable -> EDFA LINE-IN -> (PortMapping) -> LINE-OUT -> trunk cable

- [ ] **Step 7: Configure channels and create services**

Assign front ports, set statuses (lit/reserved/available mix). Create wavelength services in all lifecycle states with stitched paths through the cabled infrastructure.

- [ ] **Step 8: Verify daisy-chain topology**

Connect EXP port of one mux to COM port of a second mux via patch cable, demonstrating the upgrade/expansion use case.

- [ ] **Step 9: Run and verify**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py create_wdm_sample_data --flush
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```

- [ ] **Step 10: Commit**

```bash
git add netbox_wdm/management/commands/create_wdm_sample_data.py
git commit -m "feat: rebuild sample data with realistic WDM topologies and cabling"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: Update CLAUDE.md architecture**

Document MUX/DEMUX port pattern, fiber_type, trunk role, EXP/1310 as COM positions, DeviceType tab.

- [ ] **Step 2: Update README models table**

Add new fields to model descriptions.

- [ ] **Step 3: Update CHANGELOG**

Add entries under `[Unreleased]` for all changes.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md CHANGELOG.md
git commit -m "docs: update documentation for dual port support and DeviceType tab"
```

---

## Deferred

See `docs/TODO.md` for:
- ROADM multi-channel-per-port (relaxed unique constraint)
- OADM node type (passive inline add/drop)
- Port template auto-generation wizard
- Red/Blue band deployments (Side-A/Side-B)
- EXP/MON/1310 as explicit WDM-aware entities
