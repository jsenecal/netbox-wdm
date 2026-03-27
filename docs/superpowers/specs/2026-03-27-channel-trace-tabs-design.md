# WdmChannel Trace & Hops Tabs

## Problem

The WdmChannel detail page shows only its own attributes (node, wavelength, ports, status). There's no way to see the full wavelength path this channel belongs to, the physical cable route between nodes, or which other devices participate in the same wavelength.

## Design

### Two New Tabs on WdmChannel Detail Page

#### 1. Trace Tab — Interactive D3.js Visualization

An interactive SVG rendering of the full end-to-end wavelength path, including the DCIM cable trace between each pair of WDM nodes.

**Visual structure:** Vertical layout (matching NetBox's native trace style). Each segment shows:
- **WDM node box**: device name, channel label, wavelength, status badge, MUX/DEMUX port names
- **Cable trace between nodes**: the full physical path from NetBox's CablePath — patch panels, intermediate devices, cables with labels/colors
- **Current channel's node** highlighted with a distinct border/color

**Interactivity (D3.js):**
- Zoom and pan via D3 zoom behavior (scroll to zoom, drag to pan)
- Hover on any element shows tooltip with details (port names, cable IDs, device info)
- Click on any WDM node, device, port, or cable navigates to its NetBox detail page
- Reset zoom button

**Data source:** A new API endpoint on WdmChannel that returns:
1. The wavelength path's hop list (from `get_stitched_path()`)
2. For each consecutive pair of hops, the DCIM cable trace between their trunk ports

To get the DCIM cable trace between hops: query `CablePath` objects that contain the TX rear port of node N, then extract the path segment up to the RX rear port of node N+1. This gives us all intermediate devices and cables.

**Theme support:** Uses `--wdm-*` CSS variables. Reads `data-bs-theme` for dark/light mode. Node colors use existing badge status classes.

#### 2. Hops Tab — Table View

A standard NetBox-style table listing each WDM node in the wavelength path sequence.

**Columns:**
| Column | Content | Linked to |
|--------|---------|-----------|
| # | Sequence number | — |
| Device | Device name | Device detail |
| Channel | Channel label | WdmChannel detail |
| Wavelength | nm value | — |
| MUX Port | Front port name | FrontPort detail |
| DEMUX Port | Front port name | FrontPort detail |
| Status | Connection badge | — |

- Current channel's row highlighted with a background color
- Uses standard NetBox table classes

### When No Wavelength Path Exists

If the channel is not part of any wavelength path (unconnected node), both tabs show an info alert: "This channel is not part of a discovered wavelength path."

### New Files

| File | Purpose |
|------|---------|
| `netbox_wdm/static/netbox_wdm/src/channel-trace.ts` | D3.js trace visualization component |
| `netbox_wdm/static/netbox_wdm/src/channel-trace-types.ts` | TypeScript types for trace data |
| `netbox_wdm/static/netbox_wdm/css/channel-trace.css` | Trace-specific styles |
| `netbox_wdm/templates/netbox_wdm/wdmchannel_trace_tab.html` | Trace tab template |
| `netbox_wdm/templates/netbox_wdm/wdmchannel_hops_tab.html` | Hops tab template |

### Modified Files

| File | Change |
|------|--------|
| `netbox_wdm/views.py` | Add `WdmChannelTraceView` and `WdmChannelHopsView` registered tabs |
| `netbox_wdm/api/views.py` | Add `trace` action on `WdmChannelViewSet` returning path + cable traces |
| `bundle.cjs` | Add channel-trace entry point |

### API Endpoint

`GET /api/plugins/wdm/wdm-channels/{id}/trace/`

Returns:
```json
{
  "channel_id": 1,
  "wavelength_path_id": 5,
  "wavelength_nm": 1560.61,
  "grid_position": 1,
  "is_complete": true,
  "is_active": true,
  "hops": [
    {
      "sequence": 1,
      "node_id": 10,
      "node_name": "MUX-A",
      "node_url": "/dcim/devices/10/",
      "channel_id": 1,
      "channel_label": "C21",
      "channel_url": "/plugins/wdm/wdm-channels/1/",
      "wavelength_nm": 1560.61,
      "mux_port": {"id": 100, "name": "CH1-MUX", "url": "/dcim/front-ports/100/"},
      "demux_port": {"id": 101, "name": "CH1-DEMUX", "url": "/dcim/front-ports/101/"},
      "is_origin": true
    }
  ],
  "cable_segments": [
    {
      "from_hop": 1,
      "to_hop": 2,
      "path": [
        {"type": "rear_port", "id": 50, "name": "COM-TX", "device": "MUX-A", "url": "/dcim/rear-ports/50/"},
        {"type": "cable", "id": 200, "label": "Trunk-1", "status": "connected", "color": "ff0000", "url": "/dcim/cables/200/"},
        {"type": "rear_port", "id": 60, "name": "COM-RX", "device": "MUX-B", "url": "/dcim/rear-ports/60/"}
      ]
    }
  ]
}
```

The `cable_segments` array contains one entry per hop-to-hop link. Each `path` array lists every physical element in sequence: rear ports, cables, front ports, patch panels — everything from the DCIM cable trace between the two WDM nodes.

### D3.js Component

TypeScript class `ChannelTrace` in `channel-trace.ts`:
- Receives trace JSON data from a `<script type="application/json">` block in the template
- Creates SVG with D3, vertical layout
- Renders WDM node boxes with channel info
- Renders cable segments between nodes (intermediate devices, cables)
- Applies D3 zoom behavior to the SVG
- Tooltip div positioned on hover
- All elements get `<a>` wrappers or click handlers for navigation
- Reads theme from `document.documentElement.dataset.bsTheme`

Built via esbuild to `dist/channel-trace.min.js` (IIFE).
