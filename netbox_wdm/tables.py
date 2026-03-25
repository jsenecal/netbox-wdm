import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, columns

from .models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


class WdmDeviceTypeProfileTable(NetBoxTable):
    pk = columns.ToggleColumn()
    device_type = tables.Column(linkify=True, verbose_name=_("Device Type"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmDeviceTypeProfile
        fields = ("pk", "id", "device_type", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device_type", "node_type", "grid", "actions")


class WdmChannelTemplateTable(NetBoxTable):
    pk = columns.ToggleColumn()
    profile = tables.Column(linkify=True, verbose_name=_("Profile"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    mux_front_port_template = tables.Column(linkify=True, verbose_name=_("MUX Front Port Template"))
    demux_front_port_template = tables.Column(linkify=True, verbose_name=_("DEMUX Front Port Template"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmChannelTemplate
        fields = (
            "pk",
            "id",
            "profile",
            "grid_position",
            "label",
            "wavelength_nm",
            "mux_front_port_template",
            "demux_front_port_template",
            "actions",
        )
        default_columns = (
            "pk",
            "profile",
            "grid_position",
            "label",
            "wavelength_nm",
            "mux_front_port_template",
            "actions",
        )


class WdmNodeTable(NetBoxTable):
    pk = columns.ToggleColumn()
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmNode
        fields = ("pk", "id", "device", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device", "node_type", "grid", "actions")


class WdmTrunkPortTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    rear_port = tables.Column(linkify=True, verbose_name=_("Rear Port"))
    direction = tables.Column(verbose_name=_("Direction"))
    position = tables.Column(verbose_name=_("Position"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmTrunkPort
        fields = ("pk", "id", "wdm_node", "rear_port", "direction", "position", "actions")
        default_columns = ("pk", "wdm_node", "rear_port", "direction", "position", "actions")


class WavelengthChannelTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    mux_front_port = tables.Column(linkify=True, verbose_name=_("MUX Front Port"))
    demux_front_port = tables.Column(linkify=True, verbose_name=_("DEMUX Front Port"))
    status = tables.Column(verbose_name=_("Status"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthChannel
        fields = (
            "pk",
            "id",
            "wdm_node",
            "grid_position",
            "label",
            "wavelength_nm",
            "mux_front_port",
            "demux_front_port",
            "status",
            "actions",
        )
        default_columns = ("pk", "label", "grid_position", "wavelength_nm", "mux_front_port", "status", "actions")


class WavelengthServiceTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    status = tables.Column(verbose_name=_("Status"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    tenant = tables.Column(linkify=True, verbose_name=_("Tenant"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthService
        fields = ("pk", "id", "name", "status", "wavelength_nm", "tenant", "description", "actions")
        default_columns = ("pk", "name", "status", "wavelength_nm", "tenant", "actions")
