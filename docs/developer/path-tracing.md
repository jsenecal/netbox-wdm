# Wavelength Path Tracing

`netbox_wdm/trace.py` discovers end-to-end wavelength paths by walking the
NetBox cable plant. The user-facing summary is in
[Wavelength Paths and Circuits](../user/circuits.md); this page covers the
algorithm internals, the multi-terminated cable handling, the multi-
degree node logic, and the validity checks.

## Entry points

| Function | Purpose |
|----------|---------|
| `trace_wavelength_path(channel)` | Returns a `TraceResult` (channels in order, plus `is_complete`/`is_active`/`is_valid`) for one start channel. |
| `rebuild_wavelength_paths_for_node(node)` | Wrapper that retraces every grid position on a node and persists the result as `WdmWavelengthPath` + `WdmWavelengthPathChannel` rows. Wrapped in `transaction.atomic`. |

`rebuild_wavelength_paths_for_node` is what the post-save and post-delete
signals call (via `transaction.on_commit`) when a relevant DCIM or WDM
object changes. There is no UI button or batch job; the algorithm runs
end-to-end on every change.

## Walk shape

The trace alternates two operations:

- **Internal pass-through.** From a FrontPort on a non-WDM device, follow
  the device's `dcim.PortMapping` to the matching RearPort.
- **External cable.** From a RearPort or FrontPort, follow the
  `dcim.Cable` to the next device's port.

A path is a sequence of WDM nodes. The trace records one `WdmChannel` per
node along the way -- one entry per node, not one entry per cable.
Intermediate non-WDM devices (patch panels, EDFAs) appear in the cable
chain between two WDM channel entries but are not channel rows
themselves; the trace visualisation reads them out of the cable
terminations.

## Origin discovery (`_find_origin`)

`trace_wavelength_path` always starts by finding the **origin** node for
the channel's grid position. It walks backward from the start channel
through RX line ports until no further predecessor exists.

For each candidate predecessor it verifies that:

1. The predecessor's TX line port is the one connected to the current
   node's RX line port. If the cable lands on the predecessor's RX line
   port, it is not an origin -- it is a sibling on a misconfigured
   trunk.
2. The predecessor has a `WdmChannel` at the same grid position. A node
   that does not carry the wavelength is skipped.

On multi-degree nodes (ROADMs) every RX line port is tried. The first one
that yields a valid predecessor is followed. Visited nodes are tracked to
guarantee termination.

## Forward walk

From the origin, the trace walks forward via TX line ports, recording
each WDM node it hits. On multi-degree nodes it tries **every** TX line
port and prefers the one that leads to an unvisited node. This is the
mechanism that makes a single wavelength path span MUX-A -> ROADM ->
MUX-B without code knowing in advance which of the ROADM's two TX
directions is the express side.

The walk stops when:

- No further TX line port leads to an unvisited node, or
- The cable from the chosen TX is not connected (path ends but is still
  recorded; `is_active` will become false), or
- The far end is not a `WdmLinePort` (path ends at a non-WDM device).

## Cable-chain traversal

NetBox represents cables as `dcim.Cable` plus a list of
`dcim.CableTermination` rows, and it already ships a walker that follows
them: `CablePath.from_origin`. The plugin delegates to it rather than
following cables itself, through one helper:

- `core_walk.walk_from_rear_port(rp)` -- traces the chain leaving a rear
  port and returns the ordered node groups core recorded for it
  (`CablePath.path_objects`: terminations and the links between them,
  starting with the origin).

Both consumers read that one walk. `trace._get_far_end_node` scans it for
the first rear port carrying a `WdmLinePort` -- that is the next WDM node
along the chain. `views._trace_cable_segment` renders every object in it
as a `CableSegmentItem` for the trace diagram.

Delegating buys the permutations core already handles:

```text
[WDM-A.RP] --(cable)--> [PP-A.FP] --(internal)--> [PP-A.RP]
        --(cable)--> [PP-B.RP] --(internal)--> [PP-B.FP]
        --(cable)--> [WDM-B.RP]
```

...and equally a panel entered at its rear face, panels cascaded
rear-to-front (`PP-A.RP --(cable)--> PP-B.FP`), chains of any length, and
the A-to-Z hop across a `circuits.CircuitTermination` pair, which joins
two halves of a fibre run with no cable of its own. Core resolves each
cable's strand pairing through the cable profile, so a duplex trunk
follows the intended fibre; unprofiled cables take core's positionless
branch.

Walk results are **ephemeral**. Nothing is written to core's `CablePath`
table: core's signal handlers retrace or delete every row whose `_nodes`
match a changed cable, so a plugin-created row would not survive the
plugin's own port mappings being rebuilt.

### Bounding the walk

Core's walker carries no visited set and no hop bound -- a cabling loop
spins forever -- and these walks run inside signal handlers where that
would hang a worker. `walk_from_rear_port` therefore runs a structural
pre-scan (`_survey_chain`) before handing the chain to core. The pre-scan
follows the same `link_peers` strand resolution, crosses port mappings
and circuit terminations, and keeps a visited set. It refuses the walk
and logs a warning when the chain revisits a port, or when it is still
going after `max_trace_hops` cable segments (plugin setting, default
100). In both cases the trace comes back empty rather than incomplete or
hung.

## Validity flags

`trace_wavelength_path` returns three booleans that map to fields on
`WdmWavelengthPath`:

- **`is_complete`.** True when both the first and last channel in the
  path have a client front port assigned (`mux_front_port_id` or
  `demux_front_port_id` non-null). False during install.
- **`is_active`.** True when every cable along the trace has
  `status = connected` and the path has at least two hops. The trace
  inspects `Cable.status` as it follows each TX rear port.
- **`is_valid`.** True unless the trace detects a TX-to-TX miscable.
  `_check_far_end_role` checks each far-end `WdmLinePort.role`; if a TX
  cable lands on a TX (instead of RX or BIDI) on the next node, the
  path is recorded but flagged invalid. This is the most common
  patching mistake -- forgetting to flip TX/RX at the far end.

## Persisting paths (`rebuild_wavelength_paths_for_node`)

The rebuild loop iterates every distinct `grid_position` on the node and
calls `trace_wavelength_path` for one channel at each position. Then:

- If the trace produced fewer than 2 channels, any existing path whose
  channel set is a subset of the trace result is deleted. (This is how
  paths are torn down when a node loses connectivity.)
- Otherwise, an existing `WdmWavelengthPath` whose `path_channels` are
  the **same channels in the same sequence** is reused. Both directional
  paths in a duplex topology have the same set of channels but reverse
  sequences, so identity-by-set is not enough -- order matters.
- A new path object is created when no match exists.
- Through-table rows (`WdmWavelengthPathChannel`) are rewritten on every
  call.

The final cleanup deletes any `WdmWavelengthPath` left without
`path_channels` (orphan rows).

## Signal scheduling and atomic blocks

The signal handlers in `netbox_wdm/signals.py` schedule
`rebuild_wavelength_paths_for_node` on `transaction.on_commit`. This is
correct for normal NetBox operation, where each save runs in its own
transaction.

Code that builds a topology and inspects paths in the same atomic block
(integration tests, the sample-data command) needs to invoke
`rebuild_wavelength_paths_for_node` directly -- otherwise the rebuild
fires only after the outer atomic returns, and the assertions run before
paths exist.

## Performance characteristics

- The walk is bounded at `max_trace_hops` cable segments (plugin setting,
  default 100), so worst-case node-traversal is O(max_trace_hops) per
  grid position.
- Each walk costs the pre-scan plus core's own traversal. Both are
  memoized per rebuild pass by `TraceCache.walk`, so the grid positions
  after the first are served from memory.
- `rebuild_wavelength_paths_for_node` runs one trace per grid position,
  so a 44-channel DWDM node is bounded at 44 traces per rebuild.
- Tracing is read-mostly except for the persistence step; on a
  no-change rebuild only the through-table is rewritten and the
  underlying path row stays.

For very large topologies (hundreds of nodes, dozens of cables per
rebuild) consider batching the rebuild via a queue rather than firing
on every signal -- the trace is correct but the constant-cost overhead
of loading channels and cable terminations adds up.

## Where to look in code

| Concern | Location |
|---------|----------|
| Algorithm | `netbox_wdm/trace.py` |
| Signal hooks | `netbox_wdm/signals.py` |
| Models | `netbox_wdm/models.py` (`WdmWavelengthPath`, `WdmWavelengthPathChannel`) |
| Trace API endpoint | `WdmChannelViewSet.trace` in `netbox_wdm/api/views.py` |
| Trace dataclasses (used by the trace API and the visualisation) | `netbox_wdm/dataclasses.py` |
