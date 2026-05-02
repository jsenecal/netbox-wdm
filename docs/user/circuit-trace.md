# Circuit Trace Visualisation

Each `WdmCircuit` detail page has a **Trace** tab that renders an interactive
horizontal flow diagram of every wavelength path attached to the circuit.
The same renderer powers the per-channel **Trace** tab on `WdmChannel` detail
pages.

## What you see

The diagram is an SVG canvas with zoom and pan support, drawn by D3.js. For
each path attached to the circuit:

- **Devices** are NetBox-style boxes. WDM nodes get a teal header; patch
  panels and other intermediate devices get a purple header.
- **Ports** sit flush with the device edges. Channel front ports
  (MUX/DEMUX) appear on the client side of WDM nodes; trunk rear ports
  appear on the trunk side.
- **Cables** are drawn between consecutive devices and use the
  `Cable.color` field for their stroke colour.
- **Internal routing** (PortMappings, channel-to-COM links, ROADM
  pass-through) is shown as faint dashed bezier curves so the inside of
  each device is legible.
- A central **badge** at each cable hop fans cables in and out in an
  hourglass pattern when several wavelengths share the same physical run.

The visual conventions follow `docs/developer/style-guide.md`; CSS custom
properties keep the diagram in sync with NetBox dark and light modes
automatically.

## Interactivity

Hovering or tapping a port highlights the full wavelength path that passes
through it. Highlighting includes:

- The full chain of cables, internal links, and port boxes along the path.
- For shared ports such as COM rear ports or patch panel ports, **every**
  path that passes through that port lights up at once.
- For per-channel ports (MUX or DEMUX on a specific channel), only that
  channel's path highlights.

When a trace data set is empty (the circuit has no attached paths) the tab
shows an empty state. The data sent to the front end is the
`ChannelTraceData` dataclass, serialised as JSON in the template context as
`trace_data_list_json`.

## How the data is built

The Django view `WdmCircuitTraceView` (and the per-channel
`WdmChannelTraceView`) call `_build_trace_data_for_path()` to produce the
JSON. For each path the function:

1. Loads every `WdmWavelengthPathChannel` row in `sequence` order.
2. Builds a `PathElement` per WDM node, capturing names, URLs, and the
   client MUX/DEMUX ports.
3. For each adjacent pair of nodes, calls `_trace_cable_segment` to follow
   the trunk cable chain and collect every cable, rear port, and front port
   along the way.
4. For multi-TX nodes (ROADMs) `_trace_cable_segment` also picks the
   correct TX rear port by checking which one's cable chain reaches the next
   node.

The resulting `ChannelTraceData` mirrors the dataclass in
`netbox_wdm/dataclasses.py` and is rendered by `circuit-trace.ts`.

## Limitations

- The renderer assumes path entries follow physical cabling. If signals
  have not yet rebuilt the wavelength path after a recent change, the
  trace can be momentarily empty; reload after a few seconds.
- A circuit with hundreds of paths can be slow to render. Consider
  splitting bonded services into multiple circuits if they grow that large.
- The visualisation is read-only; it has no editing affordances. Use the
  Wavelength Editor or the cable plant tools in NetBox to modify the
  underlying data.
