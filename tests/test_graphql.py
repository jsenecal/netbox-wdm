"""Smoke tests for GraphQL types and schema."""

import pytest

from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis


@pytest.mark.django_db
class TestGraphQLImports:
    def test_types_import(self):
        from netbox_wdm.graphql.types import (
            WdmChannelPlanType,
            WdmChannelType,
            WdmCircuitType,
            WdmLinePortPlanType,
            WdmLinePortType,
            WdmNodeInstanceType,
            WdmProfileType,
        )

        assert WdmProfileType is not None
        assert WdmChannelPlanType is not None
        assert WdmNodeInstanceType is not None
        assert WdmLinePortType is not None
        assert WdmLinePortPlanType is not None
        assert WdmChannelType is not None
        assert WdmCircuitType is not None

    def test_filters_import(self):
        from netbox_wdm.graphql.filters import (
            WdmChannelFilter,
            WdmCircuitFilter,
            WdmLinePortPlanFilter,
            WdmNodeFilter,
            WdmProfileFilter,
        )

        assert WdmProfileFilter is not None
        assert WdmNodeFilter is not None
        assert WdmChannelFilter is not None
        assert WdmCircuitFilter is not None
        assert WdmLinePortPlanFilter is not None

    def test_channel_filter_has_module_id(self):
        from netbox_wdm.graphql.filters import WdmChannelFilter

        field_names = {f.name for f in WdmChannelFilter.__strawberry_definition__.fields}
        assert "module_id" in field_names

    def test_schema_import(self):
        from netbox_wdm.graphql.schema import schema

        assert isinstance(schema, list)
        assert len(schema) == 1

    def test_schema_exposes_line_port_plan_query_fields(self):
        from netbox_wdm.graphql.schema import WdmQuery

        field_names = {f.name for f in WdmQuery.__strawberry_definition__.fields}
        assert "wdm_line_port_plan" in field_names
        assert "wdm_line_port_plan_list" in field_names

    def test_profile_type_exposes_line_port_plans(self):
        from netbox_wdm.graphql.types import WdmProfileType

        field_names = {f.name for f in WdmProfileType.__strawberry_definition__.fields}
        assert "line_port_plans" in field_names

    def test_plugin_config_registers_graphql_schema(self):
        """Regression guard: netbox_wdm's schema module was never wired up.

        PluginConfig.graphql_schema was unset, so NetBox's default resource
        lookup (which expects a single-level `<module>.<attr>` path) could
        not resolve the two-level `graphql.schema` package path. The plugin's
        WdmQuery was therefore never merged into NetBox's live GraphQL
        schema, even though every import-level test here passed.
        """
        from netbox_wdm import NetBoxWDMConfig

        assert NetBoxWDMConfig.graphql_schema == "graphql.schema.schema"


@pytest.mark.django_db
class TestGraphQLSchemaWiring:
    """Checks that exercise the fully merged NetBox schema, not just this plugin's own module.

    Import-only assertions above catch broken declarations but cannot catch a
    plugin schema that fails to merge into NetBox's live schema, or filter
    classes that are defined but never attached to a type. Both failure
    modes previously existed here silently.
    """

    def test_line_port_plan_query_fields_reach_the_live_schema(self):
        from netbox.graphql.schema import schema

        sdl = schema.as_str()
        assert "wdm_line_port_plan_list(filters: WdmLinePortPlanFilter): [WdmLinePortPlanType!]!" in sdl
        assert "wdm_line_port_plan: WdmLinePortPlanType!" in sdl

    def test_channel_module_id_filter_reaches_the_live_schema(self):
        from netbox.graphql.schema import schema

        sdl = schema.as_str()
        assert "wdm_channel_list(filters: WdmChannelFilter): [WdmChannelType!]!" in sdl
        assert "module_id: Int" in sdl


@pytest.mark.django_db
class TestGraphQLModuleFields:
    """Module-scoped channels and line ports must surface through the GraphQL schema."""

    def test_channel_type_exposes_module_field(self):
        from netbox_wdm.graphql.types import WdmChannelType

        field_names = {f.name for f in WdmChannelType.__strawberry_definition__.fields}
        assert "module" in field_names

    def test_module_scoped_channel_resolves_its_module(self, wdm_site, wdm_manufacturer, wdm_roles):
        mt_cassette = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-GQL", mt_cassette)

        module_channels = bundle.node.channels.filter(module__isnull=False)
        assert module_channels.exists()
        for channel in module_channels:
            assert channel.module_id in {module.id for module in bundle.modules.values()}
