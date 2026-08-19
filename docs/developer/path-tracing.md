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

## Cable-following helpers

NetBox represents cables as `dcim.Cable` plus a list of
`dcim.CableTermination` rows. All cable hops resolve through one shared
helper:

- `resolve_cable_far_end(port)` -- given a RearPort or FrontPort (a fresh
  instance carrying its denormalized cable fields), returns the far-end
  port paired with it on its cable strand, whatever its type. This is
  also what the trace visualisation in `views.py` uses
  (`_follow_cable_far_end`).
- `_index_paired_far_end(port)` -- the legacy fallback for unprofiled
  cables (see below).
- `_resolve_rearport_cable(rp, visited)` -- glue function that follows a
  trunk cable, then a single pass-through device, then another trunk
  cable. This is what makes patch panel pairs invisible to the path
  hop count.

Strand pairing on **multi-terminated cables** (a duplex link is one
cable with two A-side ports and two B-side ports) is resolved through
the NetBox 4.6+ **cable profile**. A profiled cable persists a
`connector` on every `CableTermination`, and `link_peers` maps connector
N on one end to connector N on the other (for symmetric profiles such as
`trunk-2c1p`). That stored pairing is authoritative: it does not depend
on row creation order and survives re-terminations.

Cables without a profile have no stored strand identity, so
`resolve_cable_far_end` falls back to `_index_paired_far_end`: the Nth
termination on one end (pk order) is presumed to pair with the Nth on
the other end. This is a guess -- it breaks silently if a termination
row is ever recreated out of order -- so every use logs a warning naming
the cable. Assigning a profile to the cable moves it to the
authoritative path.

## Pass-through device traversal

`_resolve_rearport_cable` handles the patch-panel case explicitly:

```text
[WDM-A.RP] --(cable)--> [PP-A.FP] --(internal)--> [PP-A.RP]
        --(cable)--> [PP-B.RP] --(internal)--> [PP-B.FP]
        --(cable)--> [WDM-B.RP]
```

The function:

1. Follows the first cable from the WDM RearPort to the patch panel
   FrontPort.
2. Looks up the patch panel's `PortMapping` to translate FP -> RP at
   the same position.
3. Follows the inter-PP trunk cable RP -> RP.
4. Translates RP -> FP on the second PP via its `PortMapping`.
5. Follows the second cable from the PP FrontPort to the WDM RearPort.

Each step's `cable_end + index` is matched, so multi-terminated cables
in the chain still pick the right fibre.

The `visited` set tracks every rear port the walk has touched, so a
cyclic patch plant (loopback into the same PP) terminates instead of
looping forever. The outer `_get_far_end_node` also caps total hops at
the `max_trace_hops` plugin setting (default 20) and logs a warning
when the cap truncates a walk.

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

- The walk is bounded at `max_trace_hops` hops (plugin setting, default
  20), so worst-case node-traversal is O(max_trace_hops) per grid
  position.
- Each cable lookup runs a few `CableTermination` queries plus a
  `RearPort` or `FrontPort` fetch. Multi-terminated cables only widen
  the per-cable work, not the hop count.
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
