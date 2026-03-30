# Port Sync — Developer Guide

## Overview

Port sync detects and repairs drift between WDM channel grid state and the underlying NetBox port/PortMapping objects. Two fields on `WdmNode` enable cheap detection without loading all mappings on every page view.

## Detection Mechanism

### Fields

- `expected_port_hash` — SHA-256 hex digest of the correct PortMapping state, derived from WdmChannel and WdmLinePort records.
- `port_sync_valid` — Boolean flag. `False` when the actual PortMapping state on the device diverges from the expected hash.

### Hash Computation

**Expected state:** For each WdmChannel sorted by `grid_position`, for each assigned front port (mux/demux, if not null), for each matching WdmLinePort (mux to TX/BIDI, demux to RX/BIDI) sorted by `(direction, role)`, emit a tuple `(front_port_id, rear_port_id, grid_position)`. The sorted tuple list is serialized and SHA-256 hashed.

**Actual state:** All PortMapping rows on the device where the front_port belongs to a WdmChannel and the rear_port belongs to a WdmLinePort, sorted and hashed the same way.

EXP and 1310 pass-through port mappings are excluded from both hashes since they are not part of any WdmChannel.

### Signal-Driven Updates

The hash and flag are recomputed via `transaction.on_commit` callbacks when:

- **"Should be" side changes:** WdmChannel saved/deleted, WdmLinePort saved/deleted
- **"Is" side changes:** PortMapping created/deleted, FrontPort created/deleted, RearPort created/deleted

Updates use `WdmNode.objects.filter(pk=...).update(...)` to avoid triggering the WdmNode post_save signal chain.

All signals are registered in `signals.py:connect_signals()`.

## Sync Operation

Located in `netbox_wdm/port_sync.py`.

### Phase 1: Structural Repair

Compares the device's actual ports against its DeviceType template. Creates missing FrontPorts and RearPorts by name. Renamed ports with correct topology are left alone.

### Phase 2: PortMapping Reset

1. Computes the diff between expected and actual PortMappings
2. Deletes only extra PortMappings that shouldn't exist
3. Creates only missing PortMappings
4. Retraces affected CablePaths
5. Updates `expected_port_hash` and sets `port_sync_valid = True`

### Key Functions

| Function | Purpose |
|----------|---------|
| `compute_expected_port_hash(node)` | Hash of what PortMappings should exist |
| `compute_actual_port_hash(node)` | Hash of what PortMappings do exist |
| `check_port_sync(node)` | Returns `True` if hashes match |
| `compute_sync_diff(node)` | Full diff with warnings and change lists |
| `apply_sync(node)` | Execute sync, return results |

## API Endpoint

`POST /api/plugins/wdm/wdm-nodes/{id}/sync-ports/`

- Default (no param or `dry_run=true`): returns diff and warnings without applying
- `dry_run=false`: applies the sync and returns results

Response includes `port_sync_valid`, `dry_run`, `warnings` (cable paths, wavelength services), and `changes` (rear/front ports to create, port mappings to create/delete).

## Management Command

```bash
python manage.py wdm_sync_ports <pk>           # apply sync
python manage.py wdm_sync_ports <pk> --dry-run  # report only
```

Both modes print the full change report.

## Troubleshooting

**Common drift causes:**
- Manual PortMapping edits via NetBox UI or API
- Deleting FrontPorts or RearPorts from a WDM device
- Modifying rear port position counts

**Topology mismatches:** If the diff reports ports with wrong topology (wrong rear_port or wrong position), these cannot be auto-fixed. The user needs to fix the device's ports in NetBox manually, then run sync.
