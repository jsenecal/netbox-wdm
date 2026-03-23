"""Smoke tests for GraphQL types and schema."""

import pytest


@pytest.mark.django_db
class TestGraphQLImports:
    def test_types_import(self):
        from netbox_wdm.graphql.types import (
            WavelengthChannelType,
            WavelengthServiceType,
            WdmChannelTemplateType,
            WdmDeviceTypeProfileType,
            WdmNodeInstanceType,
            WdmTrunkPortType,
        )

        assert WdmDeviceTypeProfileType is not None
        assert WdmChannelTemplateType is not None
        assert WdmNodeInstanceType is not None
        assert WdmTrunkPortType is not None
        assert WavelengthChannelType is not None
        assert WavelengthServiceType is not None

    def test_filters_import(self):
        from netbox_wdm.graphql.filters import (
            WavelengthChannelFilter,
            WavelengthServiceFilter,
            WdmDeviceTypeProfileFilter,
            WdmNodeFilter,
        )

        assert WdmDeviceTypeProfileFilter is not None
        assert WdmNodeFilter is not None
        assert WavelengthChannelFilter is not None
        assert WavelengthServiceFilter is not None

    def test_schema_import(self):
        from netbox_wdm.graphql.schema import schema

        assert isinstance(schema, list)
        assert len(schema) == 1
