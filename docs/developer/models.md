# Models Reference

This page lists every concrete model defined in `netbox_wdm/models.py`, with
its fields, key constraints, and any custom save behaviour. All models
inherit from `netbox.models.NetBoxModel` unless noted otherwise.

## WdmProfile

One-to-one overlay on `dcim.DeviceType`. Holds optical metadata that
NetBox's DeviceType does not model natively.

| Field | Type | Notes |
|-------|------|-------|
| `device_type` | `OneToOneField(dcim.DeviceType)` | `related_name="wdm_profile"` |
| `node_type` | `CharField` | `WdmNodeTypeChoices` |
| `grid` | `CharField` | `WdmGridChoices` |
| `fiber_type` | `CharField` | `WdmFiberTypeChoices`; default `duplex` |
| `description` | `TextField` | Free text |

Clone fields: `node_type`, `grid`, `fiber_type`.

## WdmChannelPlan

Channel template row on a profile. Many-to-one to `WdmProfile`, one-to-one
to two `dcim.FrontPortTemplate` foreign keys (mux + demux).

| Field | Type | Notes |
|-------|------|-------|
| `profile` | `ForeignKey(WdmProfile)` | `related_name="channel_plans"`, CASCADE |
| `grid_position` | `PositiveIntegerField` | 1-based ITU grid position |
| `wavelength_nm` | `DecimalField(8,2)` | Wavelength in nm |
| `label` | `CharField(20)` | Display label |
| `mux_front_port_template` | `ForeignKey(dcim.FrontPortTemplate, SET_NULL)` | TX side |
| `demux_front_port_template` | `ForeignKey(dcim.FrontPortTemplate, SET_NULL)` | RX side, null for SF |

Constraints (database-enforced, all scoped to a single profile):

- `unique_profile_wavelength`: a wavelength_nm appears once per profile.
- `unique_profile_grid_position`: a grid_position appears once per profile.
- `unique_profile_fpt` and `unique_profile_demux_fpt`: a given FrontPortTemplate
  cannot be referenced by two channel plans on the same profile.

## WdmNode

One-to-one overlay on `dcim.Device`. Owns the device's WDM channels and
line ports.

| Field | Type | Notes |
|-------|------|-------|
| `device` | `OneToOneField(dcim.Device)` | `related_name="wdm_node"`, CASCADE |
| `node_type` | `CharField` | Same choices as profile |
| `grid` | `CharField` | Same choices as profile |
| `description` | `TextField` | Free text |
| `expected_port_hash` | `CharField(64)` | SHA-256 hex digest of expected PortMapping state |
| `port_sync_valid` | `BooleanField` | Drift flag (default True) |

Clone fields: `node_type`, `grid`.

Properties:

- `is_fixed`: True when `node_type != roadm`. Used to gate edits on
  `WdmChannel` and `WdmLinePort`.

Methods:

- `validate_channel_mapping(desired_mapping)` enforces protected-channel
  guards and port-uniqueness when the wavelength editor or `apply-mapping`
  endpoint runs.
- `_auto_populate_channels()` runs once on creation. It consumes the
  device's `device_type.wdm_profile.channel_plans` and bulk-creates one
  `WdmChannel` per plan, looking up `FrontPort` instances by name.
- `save()` wraps the parent save in `transaction.atomic` and triggers
  auto-population on creation when the node type is not `amplifier`.

## WdmLinePort

Identifies a `dcim.RearPort` as a trunk port on a WDM node, and labels its
direction and role.

| Field | Type | Notes |
|-------|------|-------|
| `wdm_node` | `ForeignKey(WdmNode)` | `related_name="line_ports"`, CASCADE |
| `rear_port` | `ForeignKey(dcim.RearPort)` | PROTECT |
| `direction` | `CharField` | `WdmLineDirectionChoices` (common / east / west) |
| `role` | `CharField` | `WdmLineRoleChoices` (tx / rx / bidi); default `bidi` |

Constraints:

- `unique_lineport_rear_port`: a rear port can be a line port on at most
  one WDM node.
- `unique_lineport_direction_role`: a node has at most one line port per
  (direction, role) pair.

`save()` and `clean()` call `_check_fixed_fields()`. On nodes where
`is_fixed=True` the `rear_port`, `direction`, and `role` are immutable
after creation.

## WdmChannel

One-per-channel record on a node. Carries the live channel-to-port
mapping and status.

| Field | Type | Notes |
|-------|------|-------|
| `wdm_node` | `ForeignKey(WdmNode)` | `related_name="channels"`, CASCADE |
| `grid_position` | `PositiveIntegerField` | Indexed into the node's grid |
| `mux_front_port` | `ForeignKey(dcim.FrontPort, SET_NULL)` | TX-side client port |
| `demux_front_port` | `ForeignKey(dcim.FrontPort, SET_NULL)` | RX-side client port |
| `status` | `CharField` | `WdmChannelStatusChoices`; default `available` |

Constraints:

- `unique_channel_grid_position`: at most one channel per (node,
  grid_position).
- `unique_node_mux_fp` and `unique_node_demux_fp`: a FrontPort can only be
  used by one channel on a given node (each conditional on the FK being
  non-null).

Properties (computed from the node's grid via `wdm_constants`):

- `label`: ITU label, e.g. `C32`, `CWDM-1310`.
- `wavelength_nm`: Decimal nm.

Fixed-node guard: only `status` is mutable when `wdm_node.is_fixed=True`.

## WdmWavelengthPath

Auto-discovered end-to-end path for a single wavelength.

| Field | Type | Notes |
|-------|------|-------|
| `grid_position` | `PositiveIntegerField` | Common to every channel on the path |
| `wavelength_nm` | `DecimalField(8,2)` | Wavelength in nm |
| `is_complete` | `BooleanField` | Both endpoints have a client port assigned |
| `is_active` | `BooleanField` | Every cable status is `connected` and length >= 2 |
| `is_valid` | `BooleanField` | False on TX-to-TX miscable detection |

Methods:

- `get_channels()` returns the path's channels in sequence order.
- `get_stitched_path()` returns the path as a list of `PathElement`
  dataclasses.
- `get_display_label()` formats as `<wavelength>nm: <node1> -> <node2> ...`.

## WdmWavelengthPathChannel

Through table linking `WdmWavelengthPath` to `WdmChannel` in sequence
order. Not a `NetBoxModel`; this is a plain `models.Model`.

| Field | Type | Notes |
|-------|------|-------|
| `path` | `ForeignKey(WdmWavelengthPath)` | CASCADE, `related_name="path_channels"` |
| `channel` | `ForeignKey(WdmChannel)` | PROTECT, `related_name="wavelength_path_entries"` |
| `sequence` | `PositiveIntegerField` | 0-based hop index |

Constraints:

- `unique_wavelength_path_channel`: a channel appears at most once per path.
- `unique_wavelength_path_sequence`: each (path, sequence) pair is unique.

## WdmCircuit

Logical service grouping over wavelength paths.

| Field | Type | Notes |
|-------|------|-------|
| `name` | `CharField(200)` | Required |
| `status` | `CharField` | `WdmCircuitStatusChoices`; default `planned` |
| `wavelength_paths` | `ManyToManyField(WdmWavelengthPath)` | M2M, `related_name="circuits"` |
| `tenant` | `ForeignKey(tenancy.Tenant, SET_NULL)` | Optional |
| `description` | `TextField` | Free text |
| `comments` | `TextField` | Free text |

Clone fields: `status`, `tenant`.

`save()` watches for status transitions:

- On move to `decommissioned`, every channel on every attached wavelength
  path is reset to status `available` and the M2M is cleared.

Methods:

- `get_stitched_paths()` returns `[(path, [PathElement, ...]), ...]`,
  reusing each path's `get_stitched_path()` helper.

## Choice sets

Defined in `netbox_wdm/choices.py`:

- `WdmNodeTypeChoices`: `terminal_mux`, `oadm`, `roadm`, `amplifier`.
- `WdmGridChoices`: `dwdm_100ghz`, `dwdm_50ghz`, `cwdm`.
- `WdmLineDirectionChoices`: `common`, `east`, `west`.
- `WdmFiberTypeChoices`: `duplex`, `single_fiber`.
- `WdmLineRoleChoices`: `tx`, `rx`, `bidi`.
- `WdmChannelStatusChoices`: `available`, `reserved`, `active`.
- `WdmCircuitStatusChoices`: `planned`, `staged`, `active`, `decommissioned`.
