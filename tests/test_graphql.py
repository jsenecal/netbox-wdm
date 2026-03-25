"""Smoke tests for GraphQL types and schema."""

import pytest


@pytest.mark.django_db
class TestGraphQLImports:
    def test_types_import(self):
        from netbox_wdm.graphql.types import (
            WdmChannelPlanType,
            WdmChannelType,
            WdmCircuitType,
            WdmLinePortType,
            WdmNodeInstanceType,
            WdmProfileType,
        )

        assert WdmProfileType is not None
        assert WdmChannelPlanType is not None
        assert WdmNodeInstanceType is not None
        assert WdmLinePortType is not None
        assert WdmChannelType is not None
        assert WdmCircuitType is not None

    def test_filters_import(self):
        from netbox_wdm.graphql.filters import (
            WdmChannelFilter,
            WdmCircuitFilter,
            WdmNodeFilter,
            WdmProfileFilter,
        )

        assert WdmProfileFilter is not None
        assert WdmNodeFilter is not None
        assert WdmChannelFilter is not None
        assert WdmCircuitFilter is not None

    def test_schema_import(self):
        from netbox_wdm.graphql.schema import schema

        assert isinstance(schema, list)
        assert len(schema) == 1
