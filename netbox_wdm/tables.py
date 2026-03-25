import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, columns

from .models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmNode,
    WdmProfile,
)


class WdmProfileTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(verbose_name=_("Profile"), linkify=True, accessor="pk")
    device_type = tables.Column(linkify=True, verbose_name=_("Device Type"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    fiber_type = tables.Column(verbose_name=_("Fiber Type"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmProfile
        fields = ("pk", "id", "name", "device_type", "node_type", "grid", "fiber_type", "description", "actions")
        default_columns = ("pk", "name", "device_type", "node_type", "grid", "fiber_type", "actions")

    def render_name(self, record):
        return str(record)


class WdmChannelPlanTable(NetBoxTable):
    pk = columns.ToggleColumn()
    profile = tables.Column(linkify=True, verbose_name=_("Profile"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    mux_front_port_template = tables.Column(linkify=True, verbose_name=_("MUX Front Port Template"))
    demux_front_port_template = tables.Column(linkify=True, verbose_name=_("DEMUX Front Port Template"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmChannelPlan
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
    name = tables.Column(verbose_name=_("Node"), linkify=True, accessor="pk")
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmNode
        fields = ("pk", "id", "name", "device", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "name", "node_type", "grid", "actions")

    def render_name(self, record):
        return str(record)


class WdmLinePortTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    rear_port = tables.Column(linkify=True, verbose_name=_("Rear Port"))
    direction = tables.Column(verbose_name=_("Direction"))
    role = tables.Column(verbose_name=_("Role"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmLinePort
        fields = ("pk", "id", "wdm_node", "rear_port", "direction", "role", "actions")
        default_columns = ("pk", "wdm_node", "rear_port", "direction", "role", "actions")


CHANNEL_TRACE_BUTTONS = (
    "{% if record.mux_front_port and record.mux_front_port.cable %}"
    "<a href=\"{% url 'dcim:frontport_trace' pk=record.mux_front_port.pk %}\" "
    'class="btn btn-primary btn-sm" title="Trace">'
    '<i class="mdi mdi-transit-connection-variant"></i></a> '
    "{% elif record.demux_front_port and record.demux_front_port.cable %}"
    "<a href=\"{% url 'dcim:frontport_trace' pk=record.demux_front_port.pk %}\" "
    'class="btn btn-primary btn-sm" title="Trace">'
    '<i class="mdi mdi-transit-connection-variant"></i></a> '
    "{% endif %}"
)


class WdmChannelTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    mux_front_port = tables.Column(linkify=True, verbose_name=_("MUX Front Port"))
    demux_front_port = tables.Column(linkify=True, verbose_name=_("DEMUX Front Port"))
    status = tables.Column(verbose_name=_("Status"))
    actions = columns.ActionsColumn(extra_buttons=CHANNEL_TRACE_BUTTONS)

    class Meta(NetBoxTable.Meta):
        model = WdmChannel
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


class WdmCircuitTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    status = tables.Column(verbose_name=_("Status"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    tenant = tables.Column(linkify=True, verbose_name=_("Tenant"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmCircuit
        fields = ("pk", "id", "name", "status", "wavelength_nm", "tenant", "description", "actions")
        default_columns = ("pk", "name", "status", "wavelength_nm", "tenant", "actions")
