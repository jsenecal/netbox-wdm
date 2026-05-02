# Architecture

netbox-wdm is built on three architectural ideas:

1. **Overlay pattern.** WDM data is layered on top of NetBox's existing DCIM
   models rather than replacing them.
2. **Position-stack alignment.** Channel `grid_position` is the single integer
   that flows from `WdmChannelPlan` through `WdmChannel` to
   `dcim.PortMapping.rear_port_position`.
3. **Signal-driven rebuilds.** Wavelength paths and port-sync state are
   recomputed automatically on transaction commit when relevant DCIM or WDM
   models change.

This page captures the contracts between modules. Later pages describe the
individual subsystems in depth.

## Overlay pattern

| WDM model | DCIM model | Cardinality |
|-----------|-----------|-------------|
| `WdmProfile` | `dcim.DeviceType` | 1:1 |
| `WdmChannelPlan` | `dcim.FrontPortTemplate` (mux + demux) | many-to-one on profile, 1:1 on each FP template |
| `WdmNode` | `dcim.Device` | 1:1 |
| `WdmLinePort` | `dcim.RearPort` | 1:1 |
| `WdmChannel` | `dcim.FrontPort` (mux + demux) | many-to-one on node, 1:1 on each FP |

Every WDM model is a `netbox.models.NetBoxModel`, so it inherits tagging,
custom fields, journaling, and the standard NetBox object views.

The overlay is intentional. NetBox's DCIM stack already tracks ports,
positions, port mappings, cables, and cable paths. The plugin would have to
re-implement all of that to model WDM as a parallel concept. By overlaying,
all standard NetBox features (cabling, search, filtering, custom fields,
tags, audit trail) keep working on the underlying objects, and WDM-specific
state lives on a thin layer above.

## Position-stack alignment

Real WDM hardware multiplexes per-channel client ports onto a single COM
rear port (or pair of COM rear ports). NetBox already models this with
`PortTemplateMapping` (template-level) and `PortMapping` (instance-level):
each FrontPort can be linked to a RearPort at a specific
`rear_port_position`.

netbox-wdm uses `grid_position` as the bridge between ITU and NetBox:

- On the template side, `WdmChannelPlan.grid_position` records the channel's
  index in the ITU grid. The template author also creates one
  `PortTemplateMapping` per channel mapping `mux_front_port_template` to a
  COM rear port template at this same position.
- On the instance side, `WdmChannel.grid_position` is copied from the
  template (positions never drift across the overlay). Whenever the plugin
  emits a `PortMapping` (during `apply-mapping` or port sync), it sets
  `rear_port_position = channel.grid_position`.

This keeps `dcim.CablePath` honest: when a wavelength enters the COM rear
port it picks the right channel's front port back out, even when many
channels share the same trunk fibre.

EXP and 1310 pass-through ports use the **same** COM rear ports but at
positions **after** the channel positions. They are present in the
DeviceType templates so cable tracing knows about them, but they are not
part of any `WdmChannel`. The port-sync hash deliberately excludes them.

## Module map

The package layout follows the standard NetBox plugin structure:

| Path | Purpose |
|------|---------|
| `netbox_wdm/__init__.py` | `PluginConfig` with version, base URL, and `ready()` hook |
| `netbox_wdm/models.py` | `WdmProfile`, `WdmChannelPlan`, `WdmNode`, `WdmLinePort`, `WdmChannel`, `WdmWavelengthPath`, `WdmWavelengthPathChannel`, `WdmCircuit` |
| `netbox_wdm/choices.py` | All `ChoiceSet` enums for grid, node type, line direction/role, fibre type, channel/circuit status |
| `netbox_wdm/wdm_constants.py` | ITU grid tables and `get_channel_info(grid, position)` |
| `netbox_wdm/signals.py` | post_save / post_delete handlers that trigger path rebuilds and port-sync rechecks |
| `netbox_wdm/trace.py` | Wavelength path discovery (`trace_wavelength_path`, `rebuild_wavelength_paths_for_node`) |
| `netbox_wdm/port_sync.py` | Drift detection (`compute_*_port_hash`, `compute_sync_diff`, `apply_sync`) |
| `netbox_wdm/views.py` | All NetBox `generic.ObjectView` subclasses, including `WdmNodeWavelengthEditorView` and the trace tab views |
| `netbox_wdm/api/` | DRF serializers, viewsets, router; custom `apply-mapping`, `sync-ports`, `trace`, `stitch` actions |
| `netbox_wdm/graphql/` | strawberry-django types, filters, and schema |
| `netbox_wdm/template_content.py` | `PluginTemplateExtension` for Device and Cable detail pages |
| `netbox_wdm/navigation.py` | The `WDM` plugin menu |
| `netbox_wdm/template_content.py` | Adds the Device WDM panel and the Cable WDM circuits panel |
| `netbox_wdm/management/commands/` | `create_wdm_sample_data`, `wdm_sync_ports`, `wdm_rehash_ports` |
| `netbox_wdm/testing/` | Topology builders shared between sample data and tests |
| `netbox_wdm/static/netbox_wdm/src/` | TypeScript sources for the wavelength editor and circuit trace renderer |

## Map-layer integration

If the optional `netbox-pathways` plugin is present, `_register_map_layers()`
in `__init__.py` registers a `wdm_nodes` layer that surfaces every device
with an attached `WdmNode` on the pathways map. The registration is wrapped
in a `try/except ImportError` so it is a soft dependency.

## Plugin API imports

The plugin uses NetBox's public plugin API consistently:

| Thing | Import |
|-------|--------|
| `NetBoxModel` | `netbox.models.NetBoxModel` |
| `ChoiceSet` | `utilities.choices.ChoiceSet` |
| `NetBoxModelForm` | `netbox.forms.NetBoxModelForm` |
| `NetBoxModelFilterSet` | `netbox.filtersets.NetBoxModelFilterSet` |
| `NetBoxTable` | `netbox.tables.NetBoxTable` |
| Generic views | `netbox.views.generic` |
| `NetBoxModelSerializer` | `netbox.api.serializers.NetBoxModelSerializer` |
| `NetBoxModelViewSet` | `netbox.api.viewsets.NetBoxModelViewSet` |
| `NetBoxRouter` | `netbox.api.routers.NetBoxRouter` |
| `ViewTab`, `register_model_view` | `utilities.views` |
| `PluginTemplateExtension` | `netbox.plugins.PluginTemplateExtension` |

These imports follow NetBox 4.5's stable plugin contract.

## URL naming convention

All URL names follow `plugins:netbox_wdm:<modelname_lowercase>` for detail
views, with `_list`, `_add`, `_edit`, `_delete` suffixes. The base URL of
the plugin is `wdm/` (set in `PluginConfig.base_url`); the REST API lives
under `/api/plugins/wdm/`.
