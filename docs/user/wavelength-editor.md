# Wavelength Editor (ROADM)

The Wavelength Editor is a TypeScript UI for assigning channels to client
front ports on a ROADM in real time. It is exposed as a tab on every WDM Node
of `node_type=roadm`. Fixed nodes (terminal MUX, OADM, amplifier) do not show
the tab because their channel-to-port mapping is hardware determined.

## Where to find it

Open the WDM Node detail page for a ROADM and switch to the **Wavelength
Editor** tab. The tab is hidden when:

- the node's type is not ROADM, or
- the user lacks `netbox_wdm.change_wdmchannel` permission.

Hitting the URL directly when the node is not a ROADM returns 404.

## What you see

The editor renders a table of every channel on the node, sorted by
`grid_position`. Each row shows:

- The ITU label and wavelength.
- A dropdown of available client front ports for the **MUX** column (the TX
  side of duplex profiles).
- A dropdown of available client front ports for the **DEMUX** column (the
  RX side; hidden for single-fibre ROADMs).
- The current channel status.
- The wavelength service name, if any service currently uses this channel.

The DEMUX column only appears when the linked WDM profile reports
`fiber_type=duplex`. For single-fibre profiles the editor shows MUX-only
assignments.

## Editing rules

The editor enforces the same rules as the REST API:

- **Channel status guard.** A channel whose status is `active` or `reserved`
  cannot be remapped. The validator returns an error and the dropdown is
  effectively read-only.
- **Port uniqueness.** A given FrontPort cannot be assigned to two channels
  in the same submission.
- **Optimistic concurrency.** When the editor loads it captures the node's
  `last_updated` timestamp. If the node has been touched in the meantime the
  apply call returns `409 Conflict` and the editor prompts a reload.

These rules live in `WdmNode.validate_channel_mapping()` and the
`apply-mapping` endpoint in `netbox_wdm/api/views.py`.

## Apply

The editor batches every changed row into a single payload and submits it to
the `apply-mapping` REST action:

```
POST /api/plugins/wdm/wdm-nodes/{id}/apply-mapping/
```

with body shape:

```json
{
  "last_updated": "2026-04-27 12:34:56.789012+00:00",
  "mapping": {
    "<channel_pk>": {"mux": <front_port_pk_or_null>, "demux": <front_port_pk_or_null>}
  }
}
```

The endpoint runs in a single transaction and:

1. Validates against the rules above. On any error it aborts with HTTP 400
   and a list of error strings.
2. Updates the affected `WdmChannel.mux_front_port_id` and
   `demux_front_port_id` columns via `bulk_update`.
3. Deletes stale `dcim.PortMapping` rows for ports that are no longer
   assigned, and bulk-creates new ones for the new assignments. Each new
   mapping uses `front_port_position=1` and
   `rear_port_position=channel.grid_position`.
4. Retraces every `dcim.CablePath` that traverses the node's line port rear
   ports.

Counts of added, removed, and changed channels come back in the response,
along with the new `last_updated` timestamp so the editor can keep submitting
without reloading.

## Undo, redo, and dirty state

The TypeScript editor maintains an undo stack of every change since load.
Buttons let operators step backward or forward; the **Save** button is only
enabled while the model is dirty. Cancelling discards the stack and reloads
from the server.

## Frontend details

The editor lives in `netbox_wdm/static/netbox_wdm/src/wavelength-editor.ts`
and is built with esbuild (see `make ts-build`). The Django view that hosts
it is `WdmNodeWavelengthEditorView`; it serialises the channel and
available-port lists into an `editor_config_json` blob the page loads at
boot.

For frontend conventions (CSS variables, badges, toolbars, accessibility),
see the [Style Guide](../developer/style-guide.md).
