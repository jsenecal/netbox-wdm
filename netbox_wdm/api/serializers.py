from netbox.api.serializers import NetBoxModelSerializer

from ..models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmLinePort,
    WdmNode,
)


class WdmDeviceTypeProfileSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmDeviceTypeProfile
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


class WdmChannelTemplateSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmChannelTemplate
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
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "node_type", "grid")


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


class WavelengthChannelSerializer(NetBoxModelSerializer):
    class Meta:
        model = WavelengthChannel
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


class WavelengthServiceSerializer(NetBoxModelSerializer):
    class Meta:
        model = WavelengthService
        fields = (
            "id",
            "url",
            "display",
            "name",
            "status",
            "wavelength_nm",
            "tenant",
            "description",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status", "wavelength_nm")
