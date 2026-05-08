# Cabling and Topologies

Once your DeviceTypes are laid out and your Devices have WDM nodes and
[line ports](device-types.md#creating-line-ports), the next setup task is
cabling. The plugin auto-discovers wavelength paths from the cable plant,
but only if cables are wired in patterns it can follow. This page lists
the patterns netbox-wdm understands and the small rules that keep tracing
honest.

## What the trace follows

`trace_wavelength_path()` walks the cable plant by alternating between
two operations:

1. **Internal pass-through.** From a FrontPort, follow the device's
   `PortTemplateMapping`-derived `dcim.PortMapping` to the matching
   RearPort at the channel's `grid_position`.
2. **External cable.** From a RearPort or FrontPort, follow the
   `dcim.Cable` to the next device's port.

The tracer alternates these two operations until it finds a non-WDM
endpoint or hits a dead end. Anything you cable that fits this alternating
pattern (front -> internal -> rear -> cable -> rear -> internal -> front
on the next device, and so on) becomes part of a wavelength path.

## Single-fibre cabling

Single-fibre topologies use one `dcim.Cable` per fibre run. Each cable has
a single termination on each end:

```text
[MUX-A.COM]  --cable-->  [PP-A.RP-01]
[PP-A.FP-01] --cable-->  [PP-B.FP-01]
[PP-B.RP-01] --cable-->  [MUX-B.COM]
```

Three cables connect two single-fibre MUXes through a pair of patch
panels. The plugin treats each cable as one hop in the wavelength path.
Bidirectional traffic shares the same physical fibre, so a single
wavelength produces a single path.

The helper `cable_through_pp_pair` in `netbox_wdm.testing.cabling` is the
canonical reference for this pattern.

## Duplex (multi-terminated) cabling

Duplex topologies use **multi-terminated cables**. A single
`dcim.Cable` carries both fibres of the pair as a list of terminations:

```text
[MUX-A.COM-TX, MUX-A.COM-RX]  --cable-->  [PP-A.FP-01, PP-A.FP-02]
[PP-A.RP-01, PP-A.RP-02]      --cable-->  [PP-B.RP-01, PP-B.RP-02]
[PP-B.FP-01, PP-B.FP-02]      --cable-->  [MUX-B.COM-RX, MUX-B.COM-TX]
```

A duplex link between two MUXes via a patch panel pair therefore needs
**three cables, not six**. Each cable's `a_terminations` and
`b_terminations` are lists of two ports each.

The trace code follows the right fibre by combining two pieces of
information per hop:

- The `cable_end` (A or B) of the port on the cable.
- The position **index** of the port within its end's termination list.

Position 0 in the A-end maps to position 0 in the B-end, and so on. This
is how the tracer separates the TX leg from the RX leg through a single
multi-terminated cable.

When you wire duplex cables in the NetBox UI:

- Use the cable form's multi-termination support (a comma-separated list
  of port names on each side).
- The order of terminations on the A side defines the fibre indexing on
  that cable. The corresponding port at the same index on the B side is
  what the trace will follow.

A duplex MUX always has its TX and RX listed **in TX, RX order on the MUX
side**. On the patch panel side, list FrontPorts in the same TX, RX order
on the device-A side, and in **RX, TX order** on the device-B side, since
the TX leg of A connects to the RX leg of B and vice versa.

The helper `cable_duplex_through_pp_pair` in `netbox_wdm.testing.cabling`
is the canonical reference. The order of arguments
(`device_a_tx_rp, device_a_rx_rp, ..., device_b_rx_rp, device_b_tx_rp`)
encodes the TX/RX flip on the far side.

## MUX-to-ROADM cabling

A duplex MUX terminating on one side of a ROADM follows the same duplex
cabling pattern, but the ROADM end uses one of its line ports instead of
a `COM` rear port:

```text
[MUX.COM-TX, MUX.COM-RX]
    -- duplex via PP pair -->
[ROADM.LINE-EAST-RX, ROADM.LINE-EAST-TX]
```

Note the **swap** at the ROADM end: MUX.COM-TX talks to
ROADM.LINE-EAST-RX (TX-to-RX), and MUX.COM-RX talks to
ROADM.LINE-EAST-TX. This is the same convention as wiring two MUXes
together, only the names are different.

For MUX-to-ROADM-to-MUX pass-through, build a duplex link to each side of
the ROADM:

```text
[MUX-A]  -- duplex via PP-EA/PP-EB -->  [ROADM.LINE-EAST]
                                              ROADM
[MUX-B]  -- duplex via PP-WA/PP-WB -->  [ROADM.LINE-WEST]
```

The trace finds pass-through wavelengths automatically: when it lands on
the ROADM's RX line port, it tries every TX line port on the same node
to see which one lets the trace continue, and follows the one that
reaches an unvisited node. This is what makes a single wavelength path
span MUX-A -> PPs -> ROADM -> PPs -> MUX-B.

## Direct device-to-device cabling

Patch panels are optional. You can cable a MUX directly to another MUX
or to a ROADM with the same termination conventions; the trace just
records one fewer hop. Use this for point-to-point lab setups or for
short metro spans where the patch plant is collapsed.

## Cable status and path activation

A wavelength path's `is_active` flag turns on when:

- Every cable in the path has `status = connected`, **and**
- The path has at least two hops.

Cables with status `planned`, `decommissioning`, or any non-connected
value will produce a wavelength path object (so you can preview the
intent), but `is_active` stays false until every cable along it is
connected. Use this to plan installs in advance and flip cables to
`connected` as turn-up progresses.

## Validity checks

The trace flags a few cable-plant errors as `is_valid = false` on the
resulting wavelength path:

- **TX-to-TX miscable.** When the tracer detects that a TX rear port on
  one side connects (eventually) to a TX rear port on the other side
  through the cable plant, it marks the path invalid. This catches the
  most common patching mistake -- forgetting to flip TX/RX at the far
  end.
- **Incomplete path.** When neither end of the path has a client port
  assigned, `is_complete` is false. This is normal during install, but
  on a turned-up service it usually means the wavelength editor has not
  been used yet on a ROADM endpoint.

Both conditions are visible in the [Wavelength Paths](circuits.md) list
and on the [trace visualisation](circuit-trace.md), so you can spot
miscables without instrumenting the optical hardware.

## Updating cables

When a cable is created, modified, or deleted, `post_save` and
`post_delete` signal handlers schedule
`rebuild_wavelength_paths_for_node` on transaction commit for every WDM
node touched by the change. Path discovery is fully automatic; there is
no UI button to trigger a rebuild and no batch job that needs to run on
a schedule.

If you change the **terminations** on a duplex multi-terminated cable
(reordering them, for example), the rebuild fires and the new fibre
mapping is reflected in any path that traverses that cable. The trace
visualisation reloads on the next page hit.

## Reference helpers

The helpers in `netbox_wdm.testing.cabling` are reference implementations
of these patterns. If you provision a cable plant from a script:

```python
from netbox_wdm.testing import (
    cable_through_pp_pair,        # 3 simplex cables MUX-PP-PP-MUX
    cable_duplex_through_pp_pair, # 3 duplex (multi-term) cables MUX-PP-PP-MUX
)
```

They are not part of the runtime plugin code path; they are exposed for
test fixtures and one-off scripts that need to build realistic cable
plants quickly.
