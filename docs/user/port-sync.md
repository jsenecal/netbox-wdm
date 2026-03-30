# Port Sync

## What Is Port Sync?

WDM nodes maintain internal port mappings that connect channel front ports to trunk rear ports at specific positions. These mappings are how NetBox traces signal paths through WDM devices.

If someone edits ports or port mappings directly in NetBox (outside the WDM plugin), the internal wiring can get out of sync with the channel grid.

## The Warning Banner

When the WDM plugin detects that a node's port mappings don't match its channel grid, a yellow warning banner appears at the top of the WDM Node detail page:

> **Port mappings are out of sync with the channel grid.**

This means one or more of the following:
- PortMappings were added, deleted, or modified directly in NetBox
- FrontPorts or RearPorts were deleted from the device
- Port positions no longer match the channel grid

## What Causes Drift?

Common causes:
- Editing PortMapping objects directly via the NetBox UI or API
- Deleting FrontPorts or RearPorts from the device
- Modifying rear port position counts on RearPorts

## Sync Now

The **Sync Now** button in the warning banner repairs the port mappings:

1. **Creates missing ports** — If FrontPorts or RearPorts from the DeviceType template are missing, they are recreated.
2. **Fixes port mappings** — Extra PortMappings are removed, missing ones are created to match the channel grid.
3. **Retraces cable paths** — NetBox recalculates logical signal paths through the device.

### What Sync Preserves

- **Cables stay connected** — Sync only touches internal port mappings, not cable connections between devices.
- **Renamed ports are kept** — If you renamed a port but its topology (which rear port it connects to, at which position) is correct, sync leaves it alone.

### When to Be Careful

The warning banner shows the number of affected cable paths and any wavelength services that traverse this node. If active services are affected, the sync will retrace their paths. This is usually correct (it fixes broken tracing), but review the warnings before proceeding.

## Management Command

Administrators can sync nodes from the command line:

```bash
# Apply sync
python manage.py wdm_sync_ports <node_pk>

# Preview changes without applying
python manage.py wdm_sync_ports <node_pk> --dry-run
```

Both modes print a full report of what will change (or was changed).
