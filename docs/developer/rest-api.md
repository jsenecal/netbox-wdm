# REST API

netbox-wdm exposes its models through the standard NetBox REST API
machinery (`NetBoxModelViewSet`, `NetBoxModelSerializer`, `NetBoxRouter`)
plus a small set of plugin-specific actions. All endpoints live under:

```
/api/plugins/wdm/
```

Authentication, permissions, throttling, and pagination follow NetBox's
defaults. Every endpoint accepts and returns the same `tags`,
`custom_fields`, `created`, and `last_updated` fields exposed on other
NetBox API endpoints.

## Endpoints

| Path | Methods | Notes |
|------|---------|-------|
| `wdm-profiles/` | GET, POST | List/create WDM profiles. |
| `wdm-profiles/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-channel-plans/` | GET, POST | List/create channel plan rows. |
| `wdm-channel-plans/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-nodes/` | GET, POST | List/create WDM nodes. POST is rare; nodes are usually auto-created by signal. |
| `wdm-nodes/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-nodes/{id}/apply-mapping/` | POST | Atomic channel-to-port reassignment for ROADM nodes. |
| `wdm-nodes/{id}/sync-ports/` | POST | Drift detection / repair (`?dry_run=true` by default). |
| `wdm-line-ports/` | GET, POST | List/create line ports. |
| `wdm-line-ports/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-channels/` | GET, POST | List/create channels. POST is rare; channels are auto-populated. |
| `wdm-channels/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-channels/{id}/trace/` | GET | Returns the channel's full wavelength path trace. |
| `wdm-wavelength-paths/` | GET | List paths. Paths are model-managed; clients should not POST. |
| `wdm-wavelength-paths/{id}/` | GET | Detail. |
| `wdm-circuits/` | GET, POST | List/create circuits. |
| `wdm-circuits/{id}/` | GET, PUT, PATCH, DELETE | Detail. |
| `wdm-circuits/{id}/stitch/` | GET | Returns the end-to-end stitched paths for a circuit. |

The router registration lives in `netbox_wdm/api/urls.py`. Filterset
classes are defined in `netbox_wdm/filters.py` and wired through the
viewsets, so every list endpoint supports the same lookup-style query
parameters NetBox uses elsewhere (`?id=`, `?id__in=`, `?q=`, plus
field-specific filters).

## Custom action: `apply-mapping`

```
POST /api/plugins/wdm/wdm-nodes/{id}/apply-mapping/
```

Atomically rebinds channel-to-front-port assignments for a ROADM. The
endpoint validates against the same rules as the
[Wavelength Editor](../user/wavelength-editor.md):

- A channel in `active` or `reserved` status cannot be remapped (PROTECT
  guard).
- A FrontPort cannot be assigned to two channels in the same payload.
- Optimistic concurrency: the caller must echo the node's
  `last_updated` timestamp at editor-load time.

Request body:

```json
{
  "last_updated": "2026-04-27 12:34:56.789012+00:00",
  "mapping": {
    "<channel_pk>": {"mux": <front_port_pk_or_null>, "demux": <front_port_pk_or_null>}
  }
}
```

A legacy single-port form (`"<channel_pk>": <fp_pk>`) is still accepted
and treated as `{"mux": fp_pk, "demux": null}`.

Response (200):

```json
{
  "added": 3,
  "removed": 1,
  "changed": 5,
  "last_updated": "2026-04-27 12:35:01.123456+00:00"
}
```

Error responses:

- `400 Bad Request` with `{"errors": [<list of strings>]}` for
  validation failures.
- `409 Conflict` when the node was modified between editor load and
  apply (`last_updated` mismatch). The body carries a `detail` message
  asking the caller to reload.

The endpoint runs in a single `transaction.atomic`. Internally
`_apply_mapping` does:

1. Bulk-update `WdmChannel.mux_front_port_id` and `demux_front_port_id`.
2. Delete stale `dcim.PortMapping` rows for ports that are no longer
   assigned.
3. Bulk-create new `PortMapping` rows with `front_port_position = 1` and
   `rear_port_position = channel.grid_position`.
4. Retrace every `dcim.CablePath` that traverses the node's line port
   rear ports (`_retrace_affected_paths`).

## Custom action: `sync-ports`

```
POST /api/plugins/wdm/wdm-nodes/{id}/sync-ports/?dry_run=true|false
```

Surfaces the [port sync](../user/port-sync.md) drift detection. By
default the call is a dry run and returns the diff without writing.

Dry run response:

```json
{
  "port_sync_valid": false,
  "dry_run": true,
  "added": [...],
  "removed": [...],
  "changed": [...]
}
```

Apply (`?dry_run=false`) returns the same shape but with the changes
already persisted, and refreshes `port_sync_valid` accordingly.

The implementation calls into `netbox_wdm/port_sync.py`
(`compute_sync_diff`, `apply_sync`).

## Custom action: `trace` (channel)

```
GET /api/plugins/wdm/wdm-channels/{id}/trace/
```

Returns the full wavelength path trace for one channel. This is the
data structure the [Circuit Trace Visualisation](../user/circuit-trace.md)
renders, and it is also useful for headless integrations that need to
walk the cable plant without fetching every cable manually.

Response shape (`ChannelTraceData` from
`netbox_wdm/dataclasses.py`):

```json
{
  "channel_id": 42,
  "wavelength_path_id": 17,
  "wavelength_nm": "1550.12",
  "grid_position": 32,
  "is_complete": true,
  "is_active": true,
  "is_valid": true,
  "elements": [
    {"sequence": 0, "node_name": "MUX-A", "device_url": "/dcim/devices/1/", ...},
    {"sequence": 1, "node_name": "MUX-B", ...}
  ],
  "cable_segments": [
    {
      "from_sequence": 0,
      "to_sequence": 1,
      "items": [
        {"type": "rear_port", "id": ..., "name": "COM-TX", "device": "MUX-A", "url": "..."},
        {"type": "cable", "id": ..., "name": "Cable #1", "status": "connected", "color": "..."},
        {"type": "rear_port", "id": ..., "name": "FP-01", "device": "PP-A", "url": "..."}
      ]
    }
  ]
}
```

When the channel has no associated wavelength path the response still
returns a `ChannelTraceData` with `wavelength_path_id = null` and empty
`elements`/`cable_segments`. Clients should treat this as an empty
state, not an error.

## Custom action: `stitch` (circuit)

```
GET /api/plugins/wdm/wdm-circuits/{id}/stitch/
```

Returns the circuit's wavelength paths in their stitched, end-to-end
form. Useful for service-level reporting where a single record per path
(rather than per hop) is wanted.

Response:

```json
{
  "service_id": 7,
  "service_name": "MTL-TOR-100G-01",
  "status": "active",
  "paths": [
    {
      "wavelength_path_id": 17,
      "wavelength_nm": "1550.12",
      "is_complete": true,
      "is_active": true,
      "elements": [...]
    }
  ]
}
```

The `elements` list reuses the same `path_element_from_channel` helper
that the channel `trace` action uses, so consumers can treat both
shapes interchangeably for rendering hops.

## Filtering

Every list endpoint accepts the standard NetBox filter parameters plus
the model-specific filters declared in `netbox_wdm/filters.py`. Common
useful filters:

| Filter | Endpoints | Notes |
|--------|-----------|-------|
| `node_type` | `wdm-profiles/`, `wdm-nodes/` | `terminal_mux`, `oadm`, `roadm`, `amplifier` |
| `grid` | `wdm-profiles/`, `wdm-nodes/` | `dwdm_100ghz`, `dwdm_50ghz`, `dwdm_l_100ghz`, `dwdm_l_50ghz`, `cwdm` |
| `device_id` | `wdm-nodes/` | Match a specific device's node. |
| `wdm_node_id` | `wdm-channels/`, `wdm-line-ports/` | Filter by parent node. |
| `status` | `wdm-channels/`, `wdm-circuits/` | Channel/circuit status. |
| `grid_position` | `wdm-channels/`, `wdm-channel-plans/` | Filter to one ITU position. |
| `port_sync_valid` | `wdm-nodes/` | Boolean; useful for triage queries. |

`?q=` performs the standard NetBox search.

## Tagging and ChangeLogged

Every WDM model is a `NetBoxModel`, so every API response includes the
standard `tags`, `custom_fields`, `created`, and `last_updated` envelope.
Object changes are journaled under NetBox's normal audit log.

## Relationship to the GraphQL API

The REST API is the **only** transport for the custom actions
(`apply-mapping`, `sync-ports`, `trace`, `stitch`). The
[GraphQL API](graphql.md) covers read-only queries against the same
models and is the right tool for nested fetches; for mutations and
side-effecting actions, use REST.

## Where to look in code

| Concern | Location |
|---------|----------|
| Routing | `netbox_wdm/api/urls.py` |
| Viewsets and custom actions | `netbox_wdm/api/views.py` |
| Serializers | `netbox_wdm/api/serializers.py` |
| Filtersets (shared with the UI) | `netbox_wdm/filters.py` |
| Trace dataclasses | `netbox_wdm/dataclasses.py` |
| Port sync | `netbox_wdm/port_sync.py` |
