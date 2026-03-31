from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
)


class WdmProfileSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmProfile
        fields = (
            "id",
            "url",
            "display",
            "device_type",
            "node_type",
            "grid",
            "fiber_type",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "node_type", "grid")


class WdmChannelPlanSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmChannelPlan
        fields = (
            "id",
            "url",
            "display",
            "profile",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port_template",
            "demux_front_port_template",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "label", "wavelength_nm")


class WdmNodeSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmNode
        fields = (
            "id",
            "url",
            "display",
            "device",
            "node_type",
            "grid",
            "expected_port_hash",
            "port_sync_valid",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "node_type", "grid", "port_sync_valid")


class WdmLinePortSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmLinePort
        fields = (
            "id",
            "url",
            "display",
            "wdm_node",
            "rear_port",
            "direction",
            "role",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "direction", "role")


class WdmChannelSerializer(NetBoxModelSerializer):
    label = serializers.CharField(read_only=True)
    wavelength_nm = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = WdmChannel
        fields = (
            "id",
            "url",
            "display",
            "wdm_node",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port",
            "demux_front_port",
            "status",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "label", "wavelength_nm", "status")


class WdmWavelengthPathSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmWavelengthPath
        fields = (
            "id",
            "url",
            "display",
            "grid_position",
            "wavelength_nm",
            "is_complete",
            "is_active",
            "is_valid",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "wavelength_nm", "is_complete", "is_active")


class WdmCircuitSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmCircuit
        fields = (
            "id",
            "url",
            "display",
            "name",
            "status",
            "wavelength_paths",
            "tenant",
            "description",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status", "wavelength_paths")
