# GraphQL API

netbox-wdm extends NetBox's GraphQL schema (powered by `strawberry-django`)
with read-only types and queries for every WDM model. The schema is
served from NetBox's standard endpoint:

```
/graphql/
```

Authentication, permissions, and rate limits follow NetBox's GraphQL
defaults.

## Coverage

| Model | Type | Single query | List query |
|-------|------|--------------|------------|
| `WdmProfile` | `WdmProfileType` | `wdm_profile(id: Int!)` | `wdm_profile_list` |
| `WdmChannelPlan` | `WdmChannelPlanType` | `wdm_channel_plan(id: Int!)` | `wdm_channel_plan_list` |
| `WdmNode` | `WdmNodeInstanceType` | `wdm_node(id: Int!)` | `wdm_node_list` |
| `WdmLinePort` | `WdmLinePortType` | `wdm_line_port(id: Int!)` | `wdm_line_port_list` |
| `WdmChannel` | `WdmChannelType` | `wdm_channel(id: Int!)` | `wdm_channel_list` |
| `WdmCircuit` | `WdmCircuitType` | `wdm_circuit(id: Int!)` | `wdm_circuit_list` |

Each type extends `netbox.graphql.types.NetBoxObjectType`, so it carries
the standard NetBox envelope (`id`, `display`, `tags`, `custom_fields`,
`created`, `last_updated`) plus every model field.

`WdmWavelengthPath` is **not** exposed via GraphQL today. Use the REST
endpoint (`wdm-wavelength-paths/` or `wdm-channels/{id}/trace/`) to read
path data.

## Nested relationships

The types declare lazy lists for the relationships that benefit most
from GraphQL's nested fetching:

- `WdmProfileType.channel_plans -> [WdmChannelPlanType]`
- `WdmNodeInstanceType.line_ports -> [WdmLinePortType]`
- `WdmNodeInstanceType.channels -> [WdmChannelType]`

The other reverse relations are still reachable through the
`strawberry-django` auto-generated fields, but the explicit annotations
let clients query a node's channels in one round trip.

Example query:

```graphql
query GetNodeWithChannels($id: Int!) {
  wdm_node(id: $id) {
    id
    display
    grid
    node_type
    port_sync_valid
    line_ports {
      id
      direction
      role
      rear_port {
        id
        name
      }
    }
    channels {
      id
      grid_position
      label
      wavelength_nm
      status
    }
  }
}
```

## Filters

Filters are declared in `netbox_wdm/graphql/filters.py` and applied by
strawberry-django's filter integration. The current set is intentionally
narrow:

| Filter type | Fields |
|-------------|--------|
| `WdmProfileFilter` | `id`, `node_type`, `grid` |
| `WdmNodeFilter` | `id`, `node_type`, `grid`, `device_id` |
| `WdmChannelFilter` | `id`, `wdm_node_id`, `status`, `grid_position` |
| `WdmCircuitFilter` | `id`, `name`, `status` |

For richer filtering (port sync state, free-text search, channel-plan
counts), use the [REST API](rest-api.md) -- its filtersets are the
shared `netbox_wdm/filters.py` filtersets and cover more fields.

## Mutations

There are no GraphQL mutations and no plugin-specific custom queries.
Side-effecting operations live on the REST API:

| Operation | REST endpoint |
|-----------|---------------|
| Apply channel-to-port mapping | `POST /api/plugins/wdm/wdm-nodes/{id}/apply-mapping/` |
| Sync ports | `POST /api/plugins/wdm/wdm-nodes/{id}/sync-ports/` |
| Channel trace | `GET /api/plugins/wdm/wdm-channels/{id}/trace/` |
| Circuit stitch | `GET /api/plugins/wdm/wdm-circuits/{id}/stitch/` |

This split is intentional: GraphQL is the right tool for nested
read-only queries, REST is the right tool for transactional writes that
need optimistic concurrency, validation guards, and structured error
responses.

## Schema registration

The plugin's GraphQL schema is registered through NetBox's plugin
contract:

- `netbox_wdm/graphql/types.py` -- one `@strawberry_django.type` per
  model.
- `netbox_wdm/graphql/filters.py` -- one
  `@strawberry_django.filters.filter_type` per filterable model.
- `netbox_wdm/graphql/schema.py` -- declares `WdmQuery` with one
  `field()` per type. The `schema = [WdmQuery]` list is what NetBox
  picks up at boot to merge plugin queries into the core schema.

To add a new model to the schema:

1. Define the type in `types.py` with `@strawberry_django.type(Model,
   fields="__all__")` and any nested-relationship annotations.
2. Add a filter type in `filters.py` if you want filtered list queries.
3. Append `wdm_<name>` and `wdm_<name>_list` fields to `WdmQuery` in
   `schema.py`.

The auto-generated fields use snake_case names; clients that prefer
camelCase should configure the strawberry-django renaming option at the
NetBox level.

## Where to look in code

| Concern | Location |
|---------|----------|
| Types | `netbox_wdm/graphql/types.py` |
| Filters | `netbox_wdm/graphql/filters.py` |
| Schema registration | `netbox_wdm/graphql/schema.py` |
| Underlying models | `netbox_wdm/models.py` |
