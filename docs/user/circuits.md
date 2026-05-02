# Wavelength Paths and Circuits

Once WDM nodes are cabled to each other (directly, through patch panels, or
through ROADMs), netbox-wdm auto-discovers the **wavelength paths** between
them and lets you group those paths into **circuits** for service tracking.

## Wavelength paths

A `WdmWavelengthPath` represents one end-to-end run of a single ITU channel
across the cable plant.

| Field | Notes |
|-------|-------|
| `grid_position` | The shared grid_position across every channel on the path |
| `wavelength_nm` | Wavelength of the path |
| `is_complete` | True when both endpoints have at least one client port assigned |
| `is_active` | True when every cable in the path has status `connected` and the path has at least 2 hops |
| `is_valid` | False when the path traverses a TX-to-TX miscable |

The through table `WdmWavelengthPathChannel` orders the channels along the
path by integer `sequence` (0-indexed). Paths preserve direction: in a duplex
topology you get one path for A-to-B and a separate path for B-to-A.

## How paths are discovered

Whenever a relevant signal fires (cable created or deleted, channel saved,
port mapping changed) the plugin schedules `rebuild_wavelength_paths_for_node`
on transaction commit for every affected node. That function:

1. Iterates each unique `grid_position` on the node.
2. Calls `trace_wavelength_path()` to walk the cable plant. The tracer first
   walks backward via RX ports to find the **origin** node, then walks
   forward via TX ports collecting every hop. It tries every TX rear port on
   multi-degree nodes (ROADMs) so pass-through directions are honoured.
3. Position-matches duplex (multi-terminated) cables using `cable_end` A/B
   indexes so the right fibre is followed.
4. Persists the result as a `WdmWavelengthPath` plus one
   `WdmWavelengthPathChannel` per hop, reusing any existing path object that
   already has the same channel sequence.

Path discovery is fully automatic; there is no UI button to trigger a
rebuild.

### Validity errors

`is_valid=False` is set when the trace detects that a TX rear port on one
side connects to a TX rear port on the other side (i.e. a wiring error in
the cable plant rather than a configuration issue). The path is still saved
so it appears in the UI and can be inspected, but the visualisation flags it
as invalid.

`is_complete=False` is set when neither the first nor the last hop has a
client port assigned. This is normal for under-construction services.

`is_active=False` is set when at least one cable along the path has a
non-`connected` status, or when the path has fewer than two hops.

## Circuits

A `WdmCircuit` is a logical service grouping over one or more wavelength
paths. Use it to label customer services, lab tests, or internal links.

| Field | Notes |
|-------|-------|
| `name` | Free-form, e.g. `MTL-TOR-100G-01` |
| `status` | `planned`, `staged`, `active`, `decommissioned` |
| `wavelength_paths` | M2M to `WdmWavelengthPath` |
| `tenant` | Optional FK to `tenancy.Tenant` |
| `description` / `comments` | Free text |

Bidirectional services typically attach **both** wavelength paths (A-to-B
and B-to-A). Bonded services attach more than one wavelength's worth of
paths.

### Decommission lifecycle

When a circuit transitions to `decommissioned`, every channel on every
attached wavelength path is reset to `available` status, and the M2M is
cleared. Other lifecycle transitions are no-ops on channel status.

This is implemented in `WdmCircuit.save()`.

## PROTECT guards on channels

When a channel's status is `active` or `reserved`, the
[Wavelength Editor](wavelength-editor.md) and the `apply-mapping` API refuse
to remap its front ports. To remap, first move the channel to `available` or
remove the encompassing circuit.

## Per-cable visibility

The plugin registers a `CableWdmCircuitsPanel` template extension. Open any
`dcim.Cable` detail page and the right column lists every WDM circuit whose
wavelength paths traverse this cable. This works both for client patch
cables (terminated on FrontPorts) and for trunk cables (terminated on
RearPorts of WdmLinePorts).

## See also

- [Circuit Trace Visualisation](circuit-trace.md) for the interactive flow
  diagram on the WdmCircuit detail page.
- [Wavelength Path Tracing](../developer/path-tracing.md) for the algorithm
  internals and the duplex/single-fibre fibre-following logic.
