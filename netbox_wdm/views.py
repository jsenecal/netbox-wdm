import json

from dcim.models import DeviceType, FrontPort
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.object_actions import BulkDelete, DeleteObject, EditObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .filters import (
    WavelengthChannelFilterSet,
    WavelengthServiceFilterSet,
    WdmChannelTemplateFilterSet,
    WdmDeviceTypeProfileFilterSet,
    WdmNodeFilterSet,
    WdmTrunkPortFilterSet,
)
from .forms import (
    WavelengthChannelBulkEditForm,
    WavelengthChannelFilterForm,
    WavelengthChannelForm,
    WavelengthServiceFilterForm,
    WavelengthServiceForm,
    WavelengthServiceImportForm,
    WdmChannelTemplateForm,
    WdmDeviceTypeProfileFilterForm,
    WdmDeviceTypeProfileForm,
    WdmDeviceTypeProfileImportForm,
    WdmNodeFilterForm,
    WdmNodeForm,
    WdmNodeImportForm,
    WdmTrunkPortForm,
)
from .models import (
    WavelengthChannel,
    WavelengthService,
    WavelengthServiceChannelAssignment,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)
from .tables import (
    WavelengthChannelTable,
    WavelengthServiceTable,
    WdmChannelTemplateTable,
    WdmDeviceTypeProfileTable,
    WdmNodeTable,
    WdmTrunkPortTable,
)

# ---- WdmDeviceTypeProfile ----


class WdmDeviceTypeProfileListView(generic.ObjectListView):
    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")
    table = WdmDeviceTypeProfileTable
    filterset = WdmDeviceTypeProfileFilterSet
    filterset_form = WdmDeviceTypeProfileFilterForm


@register_model_view(WdmDeviceTypeProfile)
class WdmDeviceTypeProfileView(generic.ObjectView):
    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")


@register_model_view(WdmDeviceTypeProfile, "edit")
class WdmDeviceTypeProfileEditView(generic.ObjectEditView):
    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")
    form = WdmDeviceTypeProfileForm


@register_model_view(WdmDeviceTypeProfile, "delete")
class WdmDeviceTypeProfileDeleteView(generic.ObjectDeleteView):
    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")


class WdmDeviceTypeProfileBulkImportView(generic.BulkImportView):
    queryset = WdmDeviceTypeProfile.objects.all()
    model_form = WdmDeviceTypeProfileImportForm


class WdmDeviceTypeProfileBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmDeviceTypeProfile.objects.all()
    filterset = WdmDeviceTypeProfileFilterSet
    table = WdmDeviceTypeProfileTable


@register_model_view(WdmDeviceTypeProfile, "channel_templates", path="channel-templates")
class WdmDeviceTypeProfileChannelTemplatesView(generic.ObjectChildrenView):
    queryset = WdmDeviceTypeProfile.objects.all()
    child_model = WdmChannelTemplate
    table = WdmChannelTemplateTable
    filterset = WdmChannelTemplateFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channel Templates"),
        badge=lambda obj: obj.channel_templates.count(),
        permission="netbox_wdm.view_wdmchanneltemplate",
        weight=500,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(profile=parent)


# ---- WdmChannelTemplate ----


@register_model_view(WdmChannelTemplate)
class WdmChannelTemplateView(generic.ObjectView):
    queryset = WdmChannelTemplate.objects.select_related("profile__device_type")


@register_model_view(WdmChannelTemplate, "edit")
class WdmChannelTemplateEditView(generic.ObjectEditView):
    queryset = WdmChannelTemplate.objects.select_related("profile__device_type")
    form = WdmChannelTemplateForm


@register_model_view(WdmChannelTemplate, "delete")
class WdmChannelTemplateDeleteView(generic.ObjectDeleteView):
    queryset = WdmChannelTemplate.objects.select_related("profile__device_type")


# ---- WdmNode ----


class WdmNodeListView(generic.ObjectListView):
    queryset = WdmNode.objects.select_related("device")
    table = WdmNodeTable
    filterset = WdmNodeFilterSet
    filterset_form = WdmNodeFilterForm


@register_model_view(WdmNode)
class WdmNodeView(generic.ObjectView):
    queryset = WdmNode.objects.select_related("device")

    def get_extra_context(self, request, instance):
        channels = list(instance.channels.select_related("mux_front_port", "demux_front_port"))
        total = len(channels)

        # Utilization from actual cable connectivity, not service status
        connected = sum(
            1
            for ch in channels
            if (ch.mux_front_port and ch.mux_front_port.cable_id)
            or (ch.demux_front_port and ch.demux_front_port.cable_id)
        )
        unconnected = total - connected

        # Service status counts (informational, not utilization)
        lit = sum(1 for ch in channels if ch.status == "lit")
        reserved = sum(1 for ch in channels if ch.status == "reserved")
        available = sum(1 for ch in channels if ch.status == "available")

        return {
            "channel_count": total,
            "trunk_port_count": instance.trunk_ports.count(),
            "channel_stats": {
                "total": total,
                "connected": connected,
                "unconnected": unconnected,
                "connected_pct": round(connected / total * 100) if total else 0,
                "lit": lit,
                "reserved": reserved,
                "available": available,
            },
        }


@register_model_view(WdmNode, "edit")
class WdmNodeEditView(generic.ObjectEditView):
    queryset = WdmNode.objects.select_related("device")
    form = WdmNodeForm


@register_model_view(WdmNode, "delete")
class WdmNodeDeleteView(generic.ObjectDeleteView):
    queryset = WdmNode.objects.select_related("device")


class WdmNodeBulkImportView(generic.BulkImportView):
    queryset = WdmNode.objects.all()
    model_form = WdmNodeImportForm


class WdmNodeBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmNode.objects.all()
    filterset = WdmNodeFilterSet
    table = WdmNodeTable


@register_model_view(WdmNode, "channels", path="channels")
class WdmNodeChannelsView(generic.ObjectChildrenView):
    queryset = WdmNode.objects.all()
    child_model = WavelengthChannel
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channels"),
        badge=lambda obj: obj.channels.count(),
        permission="netbox_wdm.view_wavelengthchannel",
        weight=500,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "trunk_ports", path="trunk-ports")
class WdmNodeTrunkPortsView(generic.ObjectChildrenView):
    queryset = WdmNode.objects.all()
    child_model = WdmTrunkPort
    table = WdmTrunkPortTable
    filterset = WdmTrunkPortFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Trunk Ports"),
        badge=lambda obj: obj.trunk_ports.count(),
        permission="netbox_wdm.view_wdmtrunkport",
        weight=510,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "wavelength_editor", path="wavelength-editor")
class WdmNodeWavelengthEditorView(generic.ObjectView):
    """Live wavelength channel editor for ROADM nodes."""

    queryset = WdmNode.objects.select_related("device")
    tab = ViewTab(
        label=_("Wavelength Editor"),
        permission="netbox_wdm.change_wavelengthchannel",
        weight=600,
    )

    def get_template_name(self):
        return "netbox_wdm/wdmnode_wavelength_editor.html"

    def get_extra_context(self, request, instance):
        channels = list(
            instance.channels.select_related("mux_front_port", "demux_front_port").order_by("grid_position")
        )
        assigned_fp_ids = set()
        for ch in channels:
            if ch.mux_front_port_id:
                assigned_fp_ids.add(ch.mux_front_port_id)
            if ch.demux_front_port_id:
                assigned_fp_ids.add(ch.demux_front_port_id)
        available_ports = FrontPort.objects.filter(device=instance.device).exclude(pk__in=assigned_fp_ids)

        channel_ids = [ch.pk for ch in channels]
        svc_by_channel = {}
        for sa in WavelengthServiceChannelAssignment.objects.filter(channel_id__in=channel_ids).select_related(
            "service"
        ):
            svc_by_channel[sa.channel_id] = sa.service.name

        channel_data = []
        for ch in channels:
            channel_data.append(
                {
                    "id": ch.pk,
                    "grid_position": ch.grid_position,
                    "wavelength_nm": float(ch.wavelength_nm),
                    "label": ch.label,
                    "mux_front_port_id": ch.mux_front_port_id,
                    "mux_front_port_name": ch.mux_front_port.name if ch.mux_front_port else None,
                    "demux_front_port_id": ch.demux_front_port_id,
                    "demux_front_port_name": ch.demux_front_port.name if ch.demux_front_port else None,
                    "status": ch.status,
                    "service_name": svc_by_channel.get(ch.pk),
                }
            )

        port_data = [{"id": p.pk, "name": p.name} for p in available_ports]

        # Get fiber_type from the device type's WDM profile
        fiber_type = "duplex"
        try:
            profile = instance.device.device_type.wdm_profile
            fiber_type = profile.fiber_type
        except WdmDeviceTypeProfile.DoesNotExist:
            pass

        config = {
            "nodeId": instance.pk,
            "nodeType": instance.node_type,
            "fiberType": fiber_type,
            "lastUpdated": str(instance.last_updated),
            "applyUrl": reverse("plugins-api:netbox_wdm-api:wdmnode-apply-mapping", args=[instance.pk]),
            "channels": channel_data,
            "availablePorts": port_data,
        }
        return {"editor_config_json": json.dumps(config)}


# ---- WdmTrunkPort ----


@register_model_view(WdmTrunkPort)
class WdmTrunkPortView(generic.ObjectView):
    queryset = WdmTrunkPort.objects.select_related("wdm_node__device", "rear_port")


@register_model_view(WdmTrunkPort, "edit")
class WdmTrunkPortEditView(generic.ObjectEditView):
    queryset = WdmTrunkPort.objects.select_related("wdm_node__device", "rear_port")
    form = WdmTrunkPortForm


@register_model_view(WdmTrunkPort, "delete")
class WdmTrunkPortDeleteView(generic.ObjectDeleteView):
    queryset = WdmTrunkPort.objects.select_related("wdm_node__device", "rear_port")


# ---- WavelengthChannel ----


class WavelengthChannelListView(generic.ObjectListView):
    queryset = WavelengthChannel.objects.select_related("wdm_node", "mux_front_port", "demux_front_port")
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    filterset_form = WavelengthChannelFilterForm


@register_model_view(WavelengthChannel)
class WavelengthChannelView(generic.ObjectView):
    queryset = WavelengthChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")


@register_model_view(WavelengthChannel, "edit")
class WavelengthChannelEditView(generic.ObjectEditView):
    queryset = WavelengthChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")
    form = WavelengthChannelForm


@register_model_view(WavelengthChannel, "delete")
class WavelengthChannelDeleteView(generic.ObjectDeleteView):
    queryset = WavelengthChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")


class WavelengthChannelBulkEditView(generic.BulkEditView):
    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable
    form = WavelengthChannelBulkEditForm


class WavelengthChannelBulkDeleteView(generic.BulkDeleteView):
    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable


# ---- WavelengthService ----


class WavelengthServiceListView(generic.ObjectListView):
    queryset = WavelengthService.objects.select_related("tenant")
    table = WavelengthServiceTable
    filterset = WavelengthServiceFilterSet
    filterset_form = WavelengthServiceFilterForm


@register_model_view(WavelengthService)
class WavelengthServiceView(generic.ObjectView):
    queryset = WavelengthService.objects.select_related("tenant")


@register_model_view(WavelengthService, "trace", path="trace")
class WavelengthServiceTraceView(generic.ObjectView):
    queryset = WavelengthService.objects.select_related("tenant")
    tab = ViewTab(
        label=_("Trace"),
        permission="netbox_wdm.view_wavelengthservice",
        weight=500,
    )

    def get_template_name(self):
        return "netbox_wdm/wavelengthservice_trace_tab.html"

    def get_extra_context(self, request, instance):
        from dcim.models import CablePath

        stitched_path = instance.get_stitched_path()

        # For each hop, trace the actual cable path from the channel's mux_front_port
        for hop in stitched_path:
            hop["cable_path"] = None
            if hop.get("mux_front_port_id"):
                path = CablePath.objects.filter(
                    _nodes__contains=[{"type": "dcim.frontport", "id": hop["mux_front_port_id"]}]
                ).first()
                if path:
                    hop["cable_path"] = {
                        "is_complete": path.is_complete,
                        "is_active": path.is_active,
                        "segment_count": len(path.path) if path.path else 0,
                    }

        return {"stitched_path": stitched_path}


@register_model_view(WavelengthService, "edit")
class WavelengthServiceEditView(generic.ObjectEditView):
    queryset = WavelengthService.objects.select_related("tenant")
    form = WavelengthServiceForm


@register_model_view(WavelengthService, "delete")
class WavelengthServiceDeleteView(generic.ObjectDeleteView):
    queryset = WavelengthService.objects.select_related("tenant")


class WavelengthServiceBulkImportView(generic.BulkImportView):
    queryset = WavelengthService.objects.all()
    model_form = WavelengthServiceImportForm


class WavelengthServiceBulkDeleteView(generic.BulkDeleteView):
    queryset = WavelengthService.objects.all()
    filterset = WavelengthServiceFilterSet
    table = WavelengthServiceTable


# ---- DeviceType WDM Profile Tab ----


@register_model_view(DeviceType, "wdm_profile", path="wdm-profile")
class DeviceTypeWdmProfileView(generic.ObjectView):
    queryset = DeviceType.objects.all()
    tab = ViewTab(
        label=_("WDM Profile"),
        badge=lambda obj: WdmDeviceTypeProfile.objects.filter(device_type=obj).exists(),
        permission="netbox_wdm.view_wdmdevicetypeprofile",
        weight=1100,
    )

    def get_template_name(self):
        return "netbox_wdm/devicetype_wdm_tab.html"

    def get_extra_context(self, request, instance):
        profile = WdmDeviceTypeProfile.objects.filter(device_type=instance).first()
        channel_templates = []
        if profile:
            channel_templates = list(
                profile.channel_templates.select_related(
                    "mux_front_port_template", "demux_front_port_template"
                ).order_by("grid_position")
            )
        return {"profile": profile, "channel_templates": channel_templates}
