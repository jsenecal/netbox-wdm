# TODO

## ROADM Multi-Channel-Per-Port

Current `WavelengthChannel` model enforces a 1:1 constraint between channel and front port (`unique_node_mux_fp`, `unique_node_demux_fp`). Real ROADM hardware allows multiple wavelength channels to be added/dropped on a single "user" port (e.g., a muxponder port carrying 4 lambdas).

### What needs to change
- Relax or make conditional the unique constraint on `(wdm_node, mux_front_port)` and `(wdm_node, demux_front_port)` for ROADM node types
- The wavelength editor needs to support assigning multiple channels to the same port
- `validate_channel_mapping()` port conflict detection must allow port sharing for ROADM nodes
- Consider whether the many-to-one relationship needs a capacity/slot concept (how many channels can a single user port carry)

### ROADM Add/Drop Banks (SRGs)
- Multi-degree ROADMs group add/drop ports into "banks" or Shared Risk Groups (SRGs)
- Each bank may have 20+ port pairs sharing a common failure domain
- Consider whether the model needs a bank/SRG grouping concept or if port naming convention is sufficient

## OADM Node Type

Add `OADM` as a distinct `WdmNodeTypeChoices` value (separate from ROADM). OADMs are passive inline devices that:
- Have LINE-IN + LINE-OUT rear ports (trunk passes through)
- Drop/add a small number of specific channels (1-4) via front port pairs
- Channels not dropped pass through transparently
- Can be cascaded in series on a fiber span

### Port topology
- Rear: `LINE-IN`, `LINE-OUT` (or `LINE-EAST`, `LINE-WEST` for ring topologies)
- Front: `CH{n}-ADD`, `CH{n}-DROP` per dropped channel
- PortMappings from each channel front port to the LINE rear ports at the channel's grid position

## Port Template Auto-Generation Wizard

When a user assigns a WDM profile to a DeviceType, offer a wizard to auto-generate:
- FrontPortTemplates for all channels (MUX/DEMUX or single for BiDi)
- RearPortTemplates for COM (and EXP, 1310 if applicable)
- PortTemplateMappings linking channels to COM positions
- Good defaults based on fiber_type, grid, and node_type
- Ability to customize port naming convention before creation

## Red/Blue Band Deployments

For DWDM single-fiber bidirectional deployments with amplification:
- C-band split into Blue (~1529-1542nm, C21-C35) and Red (~1548-1561nm, C45-C60)
- One direction TX on blue, RX on red; far end reversed
- Requires Side-A / Side-B pairing at instance (WdmNode) level, not template level
- Consider adding `side` field to WdmNode (side_a, side_b, none)

## EXP/MON Ports as WDM-Aware Entities

Currently EXP and 1310 pass-through ports are modeled as regular front ports with COM rear port positions. Consider whether the WDM model should explicitly track:
- Which front ports are EXP ports (for daisy-chain topology validation)
- Which front ports are 1310 pass-through (for gray optic coexistence tracking)
- MON (monitor) ports for signal tap management
