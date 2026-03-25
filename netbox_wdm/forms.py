from dcim.models import Device, DeviceType, FrontPort, FrontPortTemplate, RearPort
from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelBulkEditForm, NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from tenancy.models import Tenant
from utilities.forms.fields import CommentField, DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.rendering import FieldSet

from .choices import (
    WdmChannelStatusChoices,
    WdmCircuitStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmNode,
    WdmProfile,
)

# --- WdmProfile ---


class WdmProfileForm(NetBoxModelForm):
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), label=_("Device Type"))

    fieldsets = (
        FieldSet("device_type", "node_type", "grid", "fiber_type", name=_("WDM Profile")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmProfile
        fields = ("device_type", "node_type", "grid", "fiber_type", "description", "tags")


class WdmProfileFilterForm(NetBoxModelFilterSetForm):
    model = WdmProfile
    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmProfileImportForm(NetBoxModelImportForm):
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmProfile
        fields = ("device_type", "node_type", "grid", "fiber_type", "description")


# --- WdmChannelPlan ---


class WdmChannelPlanForm(NetBoxModelForm):
    profile = DynamicModelChoiceField(queryset=WdmProfile.objects.all(), label=_("Profile"))
    mux_front_port_template = DynamicModelChoiceField(
        queryset=FrontPortTemplate.objects.all(), required=False, label=_("MUX Front Port Template")
    )
    demux_front_port_template = DynamicModelChoiceField(
        queryset=FrontPortTemplate.objects.all(), required=False, label=_("DEMUX Front Port Template")
    )

    fieldsets = (
        FieldSet(
            "profile",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port_template",
            "demux_front_port_template",
            name=_("Channel Plan"),
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmChannelPlan
        fields = (
            "profile",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port_template",
            "demux_front_port_template",
            "tags",
        )


# --- WdmNode ---


class WdmNodeForm(NetBoxModelForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Device"))

    fieldsets = (
        FieldSet("device", "node_type", "grid", name=_("WDM Node")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description", "tags")


class WdmNodeFilterForm(NetBoxModelFilterSetForm):
    model = WdmNode
    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmNodeImportForm(NetBoxModelImportForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description")


# --- WdmLinePort ---


class WdmLinePortForm(NetBoxModelForm):
    wdm_node = DynamicModelChoiceField(queryset=WdmNode.objects.all(), label=_("WDM Node"))
    rear_port = DynamicModelChoiceField(queryset=RearPort.objects.all(), label=_("Rear Port"))

    fieldsets = (
        FieldSet("wdm_node", "rear_port", "direction", "role", name=_("Line Port")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmLinePort
        fields = ("wdm_node", "rear_port", "direction", "role", "tags")


# --- WdmChannel ---


class WdmChannelForm(NetBoxModelForm):
    wdm_node = DynamicModelChoiceField(queryset=WdmNode.objects.all(), label=_("WDM Node"))
    mux_front_port = DynamicModelChoiceField(
        queryset=FrontPort.objects.all(), required=False, label=_("MUX Front Port")
    )
    demux_front_port = DynamicModelChoiceField(
        queryset=FrontPort.objects.all(), required=False, label=_("DEMUX Front Port")
    )

    fieldsets = (
        FieldSet(
            "wdm_node",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port",
            "demux_front_port",
            "status",
            name=_("Channel"),
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmChannel
        fields = (
            "wdm_node",
            "grid_position",
            "wavelength_nm",
            "label",
            "mux_front_port",
            "demux_front_port",
            "status",
            "tags",
        )


class WdmChannelBulkEditForm(NetBoxModelBulkEditForm):
    model = WdmChannel
    status = forms.ChoiceField(choices=WdmChannelStatusChoices, required=False)
    fieldsets = (FieldSet("status"),)
    nullable_fields = ()


class WdmChannelFilterForm(NetBoxModelFilterSetForm):
    model = WdmChannel
    status = forms.MultipleChoiceField(choices=WdmChannelStatusChoices, required=False)
    wdm_node_id = DynamicModelMultipleChoiceField(queryset=WdmNode.objects.all(), required=False, label=_("WDM Node"))

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("wdm_node_id", "status", name=_("Attributes")),
    )


# --- WdmCircuit ---


class WdmCircuitForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("name", "status", "wavelength_nm", "tenant", name=_("Circuit")),
        FieldSet("description", "comments", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmCircuit
        fields = ("name", "status", "wavelength_nm", "tenant", "description", "comments", "tags")


class WdmCircuitFilterForm(NetBoxModelFilterSetForm):
    model = WdmCircuit
    status = forms.MultipleChoiceField(choices=WdmCircuitStatusChoices, required=False)
    tenant_id = DynamicModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("status", "tenant_id", name=_("Attributes")),
    )


class WdmCircuitImportForm(NetBoxModelImportForm):
    status = forms.ChoiceField(choices=WdmCircuitStatusChoices)

    class Meta:
        model = WdmCircuit
        fields = ("name", "status", "wavelength_nm", "description", "comments")
