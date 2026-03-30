from __future__ import annotations

import json
from typing import Any

from dcim.models import DeviceType, FrontPort
from django.core.serializers.json import DjangoJSONEncoder
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.object_actions import BulkDelete, DeleteObject, EditObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .choices import WdmNodeTypeChoices
from .dataclasses import CableSegment, CableSegmentItem, ChannelTraceData, path_element_from_channel
from .filters import (
    WdmChannelFilterSet,
    WdmChannelPlanFilterSet,
    WdmCircuitFilterSet,
    WdmLinePortFilterSet,
    WdmNodeFilterSet,
    WdmProfileFilterSet,
)
from .forms import (
    WdmChannelBulkEditForm,
    WdmChannelFilterForm,
    WdmChannelForm,
    WdmChannelPlanForm,
    WdmCircuitFilterForm,
    WdmCircuitForm,
    WdmCircuitImportForm,
    WdmLinePortForm,
    WdmNodeFilterForm,
    WdmNodeForm,
    WdmNodeImportForm,
    WdmProfileFilterForm,
    WdmProfileForm,
    WdmProfileImportForm,
)
from .models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
    WdmWavelengthPathChannel,
)
from .tables import (
    WdmChannelPlanTable,
    WdmChannelTable,
    WdmCircuitTable,
    WdmLinePortTable,
    WdmNodeChannelTable,
    WdmNodeTable,
    WdmProfileTable,
    WdmWavelengthPathTable,
)

# ---- WdmProfile ----


class WdmProfileListView(generic.ObjectListView):
    queryset = WdmProfile.objects.select_related("device_type")
    table = WdmProfileTable
    filterset = WdmProfileFilterSet
    filterset_form = WdmProfileFilterForm


@register_model_view(WdmProfile)
class WdmProfileView(generic.ObjectView):
    queryset = WdmProfile.objects.select_related("device_type")


@register_model_view(WdmProfile, "edit")
class WdmProfileEditView(generic.ObjectEditView):
    queryset = WdmProfile.objects.select_related("device_type")
    form = WdmProfileForm


@register_model_view(WdmProfile, "delete")
class WdmProfileDeleteView(generic.ObjectDeleteView):
    queryset = WdmProfile.objects.select_related("device_type")


class WdmProfileBulkImportView(generic.BulkImportView):
    queryset = WdmProfile.objects.all()
    model_form = WdmProfileImportForm


class WdmProfileBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmProfile.objects.all()
    filterset = WdmProfileFilterSet
    table = WdmProfileTable


@register_model_view(WdmProfile, "channel_plans", path="channel-plans")
class WdmProfileChannelPlansView(generic.ObjectChildrenView):
    queryset = WdmProfile.objects.all()
    child_model = WdmChannelPlan
    table = WdmChannelPlanTable
    filterset = WdmChannelPlanFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channels"),
        badge=lambda obj: obj.channel_plans.count(),
        permission="netbox_wdm.view_wdmchannelplan",
        weight=500,
    )

    def get_children(self, request: Any, parent: Any) -> Any:
        return self.child_model.objects.restrict(request.user, "view").filter(profile=parent)


@register_model_view(WdmProfile, "instances", path="instances")
class WdmProfileInstancesView(generic.ObjectChildrenView):
    queryset = WdmProfile.objects.all()
    child_model = WdmNode
    table = WdmNodeTable
    actions = ()
    tab = ViewTab(
        label=_("Instances"),
        badge=lambda obj: WdmNode.objects.filter(device__device_type=obj.device_type).count(),
        permission="netbox_wdm.view_wdmnode",
        weight=510,
    )

    def get_children(self, request: Any, parent: Any) -> Any:
        return (
            self.child_model.objects.restrict(request.user, "view")
            .filter(device__device_type=parent.device_type)
            .select_related("device")
        )


# ---- WdmChannelPlan ----


@register_model_view(WdmChannelPlan)
class WdmChannelPlanView(generic.ObjectView):
    queryset = WdmChannelPlan.objects.select_related("profile__device_type")


@register_model_view(WdmChannelPlan, "edit")
class WdmChannelPlanEditView(generic.ObjectEditView):
    queryset = WdmChannelPlan.objects.select_related("profile__device_type")
    form = WdmChannelPlanForm


@register_model_view(WdmChannelPlan, "delete")
class WdmChannelPlanDeleteView(generic.ObjectDeleteView):
    queryset = WdmChannelPlan.objects.select_related("profile__device_type")


# ---- WdmNode ----


class WdmNodeListView(generic.ObjectListView):
    queryset = WdmNode.objects.select_related("device")
    table = WdmNodeTable
    filterset = WdmNodeFilterSet
    filterset_form = WdmNodeFilterForm


@register_model_view(WdmNode)
class WdmNodeView(generic.ObjectView):
    queryset = WdmNode.objects.select_related("device")

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        channels = list(instance.channels.select_related("mux_front_port", "demux_front_port"))
        total = len(channels)

        # Compute combined cable + status counts for stacked bar
        active_connected = 0
        active_disconnected = 0
        reserved_connected = 0
        reserved_disconnected = 0
        available_connected = 0
        available_disconnected = 0

        for ch in channels:
            has_cable = (ch.mux_front_port and ch.mux_front_port.cable_id) or (
                ch.demux_front_port and ch.demux_front_port.cable_id
            )
            if ch.status == "active":
                if has_cable:
                    active_connected += 1
                else:
                    active_disconnected += 1
            elif ch.status == "reserved":
                if has_cable:
                    reserved_connected += 1
                else:
                    reserved_disconnected += 1
            else:
                if has_cable:
                    available_connected += 1
                else:
                    available_disconnected += 1

        pct = lambda n: round(n / total * 100) if total else 0  # noqa: E731

        return {
            "port_sync_valid": instance.port_sync_valid,
            "channel_count": total,
            "line_port_count": instance.line_ports.count(),
            "channel_stats": {
                "total": total,
                "active_connected": active_connected,
                "active_connected_pct": pct(active_connected),
                "active_disconnected": active_disconnected,
                "active_disconnected_pct": pct(active_disconnected),
                "reserved_connected": reserved_connected,
                "reserved_connected_pct": pct(reserved_connected),
                "reserved_disconnected": reserved_disconnected,
                "reserved_disconnected_pct": pct(reserved_disconnected),
                "available_connected": available_connected,
                "available_connected_pct": pct(available_connected),
                "available_disconnected": available_disconnected,
                "available_disconnected_pct": pct(available_disconnected),
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
    child_model = WdmChannel
    table = WdmNodeChannelTable
    filterset = WdmChannelFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channels"),
        badge=lambda obj: obj.channels.count(),
        permission="netbox_wdm.view_wdmchannel",
        weight=500,
    )

    def get_children(self, request: Any, parent: Any) -> Any:
        return (
            self.child_model.objects.restrict(request.user, "view")
            .filter(wdm_node=parent)
            .select_related("mux_front_port", "demux_front_port")
        )


@register_model_view(WdmNode, "line_ports", path="line-ports")
class WdmNodeLinePortsView(generic.ObjectChildrenView):
    queryset = WdmNode.objects.all()
    child_model = WdmLinePort
    table = WdmLinePortTable
    filterset = WdmLinePortFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Line Ports"),
        badge=lambda obj: obj.line_ports.count(),
        permission="netbox_wdm.view_wdmlineport",
        weight=510,
    )

    def get_children(self, request: Any, parent: Any) -> Any:
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "wavelength_editor", path="wavelength-editor")
class WdmNodeWavelengthEditorView(generic.ObjectView):
    """Live wavelength channel editor for ROADM nodes."""

    queryset = WdmNode.objects.select_related("device")
    tab = ViewTab(
        label=_("Wavelength Editor"),
        permission="netbox_wdm.change_wdmchannel",
        visible=lambda obj: obj.node_type == WdmNodeTypeChoices.ROADM,
        weight=600,
    )

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        instance = self.get_object(**kwargs)
        if instance.node_type != WdmNodeTypeChoices.ROADM:
            from django.http import Http404

            raise Http404
        return super().get(request, *args, **kwargs)

    def get_template_name(self) -> str:
        return "netbox_wdm/wdmnode_wavelength_editor.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
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
        for wpc in (
            WdmWavelengthPathChannel.objects.filter(channel_id__in=channel_ids)
            .select_related("path")
            .prefetch_related("path__circuits")
        ):
            for circuit in wpc.path.circuits.all():
                svc_by_channel[wpc.channel_id] = circuit.name

        channel_data = []
        for ch in channels:
            channel_data.append(
                {
                    "id": ch.pk,
                    "grid_position": ch.grid_position,
                    "wavelength_nm": ch.wavelength_nm,
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
        except WdmProfile.DoesNotExist:
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
        return {"editor_config_json": json.dumps(config, cls=DjangoJSONEncoder)}


# ---- WdmLinePort ----


@register_model_view(WdmLinePort)
class WdmLinePortView(generic.ObjectView):
    queryset = WdmLinePort.objects.select_related("wdm_node__device", "rear_port")


@register_model_view(WdmLinePort, "edit")
class WdmLinePortEditView(generic.ObjectEditView):
    queryset = WdmLinePort.objects.select_related("wdm_node__device", "rear_port")
    form = WdmLinePortForm


@register_model_view(WdmLinePort, "delete")
class WdmLinePortDeleteView(generic.ObjectDeleteView):
    queryset = WdmLinePort.objects.select_related("wdm_node__device", "rear_port")


# ---- WdmWavelengthPath ----


class WdmWavelengthPathListView(generic.ObjectListView):
    queryset = WdmWavelengthPath.objects.all()
    table = WdmWavelengthPathTable


# ---- WdmChannel ----


class WdmChannelListView(generic.ObjectListView):
    queryset = WdmChannel.objects.select_related("wdm_node", "mux_front_port", "demux_front_port")
    table = WdmChannelTable
    filterset = WdmChannelFilterSet
    filterset_form = WdmChannelFilterForm


@register_model_view(WdmChannel)
class WdmChannelView(generic.ObjectView):
    queryset = WdmChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")


@register_model_view(WdmChannel, "elements", path="elements")
class WdmChannelElementsView(generic.ObjectView):
    queryset = WdmChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")
    tab = ViewTab(
        label=_("Elements"),
        badge=lambda obj: (
            obj.wavelength_path_entries.first().path.path_channels.count()
            if obj.wavelength_path_entries.exists()
            else None
        ),
        hide_if_empty=True,
        permission="netbox_wdm.view_wdmchannel",
        weight=510,
    )

    def get_template_name(self) -> str:
        return "netbox_wdm/wdmchannel_elements_tab.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        path_entry = WdmWavelengthPathChannel.objects.filter(channel=instance).select_related("path").first()
        if not path_entry:
            return {"elements": []}

        elements = []
        for entry in path_entry.path.path_channels.select_related(
            "channel__wdm_node__device",
            "channel__mux_front_port",
            "channel__demux_front_port",
        ).order_by("sequence"):
            elements.append(path_element_from_channel(entry.channel, entry.sequence))

        return {"elements": elements}


@register_model_view(WdmChannel, "trace", path="trace")
class WdmChannelTraceView(generic.ObjectView):
    queryset = WdmChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")
    tab = ViewTab(
        label=_("Trace"),
        visible=lambda obj: obj.wavelength_path_entries.exists(),
        permission="netbox_wdm.view_wdmchannel",
        weight=500,
    )

    def get_template_name(self) -> str:
        return "netbox_wdm/wdmchannel_trace_tab.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        from dataclasses import asdict

        from dcim.models import Cable, CableTermination, RearPort
        from django.contrib.contenttypes.models import ContentType

        from .models import WdmLinePort, WdmWavelengthPathChannel

        path_entry = WdmWavelengthPathChannel.objects.filter(channel=instance).select_related("path").first()
        if not path_entry:
            return {"trace_data": None, "trace_data_json": "null"}

        wl_path = path_entry.path
        elements = []
        for entry in wl_path.path_channels.select_related(
            "channel__wdm_node__device",
            "channel__mux_front_port",
            "channel__demux_front_port",
        ).order_by("sequence"):
            elements.append(path_element_from_channel(entry.channel, entry.sequence))

        # Cable segments between consecutive elements
        cable_segments: list[CableSegment] = []
        rp_ct = ContentType.objects.get_for_model(RearPort)
        hop_entries = list(wl_path.path_channels.select_related("channel__wdm_node__device").order_by("sequence"))
        for i in range(len(hop_entries) - 1):
            from_node = hop_entries[i].channel.wdm_node
            items: list[CableSegmentItem] = []

            tx_lp = (
                WdmLinePort.objects.filter(wdm_node=from_node, role__in=["tx", "bidi"])
                .select_related("rear_port")
                .first()
            )

            if tx_lp and tx_lp.rear_port.cable_id:
                items.append(
                    CableSegmentItem(
                        type="rear_port",
                        id=tx_lp.rear_port_id,
                        name=tx_lp.rear_port.name,
                        device=from_node.device.name,
                        url=tx_lp.rear_port.get_absolute_url(),
                    )
                )

                try:
                    cable = Cable.objects.get(pk=tx_lp.rear_port.cable_id)
                    items.append(
                        CableSegmentItem(
                            type="cable",
                            id=cable.pk,
                            name=cable.label or f"Cable #{cable.pk}",
                            status=cable.status,
                            color=cable.color or "",
                            url=cable.get_absolute_url(),
                        )
                    )
                except Cable.DoesNotExist:
                    pass

                far_terms = CableTermination.objects.filter(
                    cable_id=tx_lp.rear_port.cable_id, termination_type=rp_ct
                ).exclude(termination_id=tx_lp.rear_port_id)
                far_term = far_terms.first()
                if far_term:
                    far_rp = RearPort.objects.filter(pk=far_term.termination_id).select_related("device").first()
                    if far_rp:
                        items.append(
                            CableSegmentItem(
                                type="rear_port",
                                id=far_rp.pk,
                                name=far_rp.name,
                                device=far_rp.device.name,
                                url=far_rp.get_absolute_url(),
                            )
                        )

            cable_segments.append(
                CableSegment(
                    from_sequence=hop_entries[i].sequence,
                    to_sequence=hop_entries[i + 1].sequence,
                    items=items,
                )
            )

        trace_data = ChannelTraceData(
            channel_id=instance.pk,
            wavelength_path_id=wl_path.pk,
            wavelength_nm=wl_path.wavelength_nm,
            grid_position=wl_path.grid_position,
            is_complete=wl_path.is_complete,
            is_active=wl_path.is_active,
            is_valid=wl_path.is_valid,
            elements=elements,
            cable_segments=cable_segments,
        )

        return {
            "trace_data": trace_data,
            "trace_data_json": json.dumps(asdict(trace_data), cls=DjangoJSONEncoder),
        }


@register_model_view(WdmChannel, "edit")
class WdmChannelEditView(generic.ObjectEditView):
    queryset = WdmChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")
    form = WdmChannelForm


@register_model_view(WdmChannel, "delete")
class WdmChannelDeleteView(generic.ObjectDeleteView):
    queryset = WdmChannel.objects.select_related("wdm_node__device", "mux_front_port", "demux_front_port")


class WdmChannelBulkEditView(generic.BulkEditView):
    queryset = WdmChannel.objects.all()
    filterset = WdmChannelFilterSet
    table = WdmChannelTable
    form = WdmChannelBulkEditForm


class WdmChannelBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmChannel.objects.all()
    filterset = WdmChannelFilterSet
    table = WdmChannelTable


# ---- WdmCircuit ----


class WdmCircuitListView(generic.ObjectListView):
    queryset = WdmCircuit.objects.select_related("tenant")
    table = WdmCircuitTable
    filterset = WdmCircuitFilterSet
    filterset_form = WdmCircuitFilterForm


@register_model_view(WdmCircuit)
class WdmCircuitView(generic.ObjectView):
    queryset = WdmCircuit.objects.select_related("tenant")


@register_model_view(WdmCircuit, "trace", path="trace")
class WdmCircuitTraceView(generic.ObjectView):
    queryset = WdmCircuit.objects.select_related("tenant")
    tab = ViewTab(
        label=_("Trace"),
        permission="netbox_wdm.view_wdmcircuit",
        weight=500,
    )

    def get_template_name(self) -> str:
        return "netbox_wdm/wdmcircuit_trace_tab.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        stitched_path = instance.get_stitched_path()
        return {"stitched_path": stitched_path}


@register_model_view(WdmCircuit, "edit")
class WdmCircuitEditView(generic.ObjectEditView):
    queryset = WdmCircuit.objects.select_related("tenant")
    form = WdmCircuitForm


@register_model_view(WdmCircuit, "delete")
class WdmCircuitDeleteView(generic.ObjectDeleteView):
    queryset = WdmCircuit.objects.select_related("tenant")


class WdmCircuitBulkImportView(generic.BulkImportView):
    queryset = WdmCircuit.objects.all()
    model_form = WdmCircuitImportForm


class WdmCircuitBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmCircuit.objects.all()
    filterset = WdmCircuitFilterSet
    table = WdmCircuitTable


# ---- DeviceType WDM Profile Tab ----


@register_model_view(DeviceType, "wdm_profile", path="wdm-profile")
class DeviceTypeWdmProfileView(generic.ObjectView):
    queryset = DeviceType.objects.all()
    tab = ViewTab(
        label=_("WDM Profile"),
        visible=lambda obj: WdmProfile.objects.filter(device_type=obj).exists(),
        permission="netbox_wdm.view_wdmprofile",
        weight=1100,
    )

    def get_template_name(self) -> str:
        return "netbox_wdm/devicetype_wdm_tab.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        profile = WdmProfile.objects.filter(device_type=instance).first()
        channel_plans = []
        if profile:
            channel_plans = list(
                profile.channel_plans.select_related("mux_front_port_template", "demux_front_port_template").order_by(
                    "grid_position"
                )
            )
        return {"profile": profile, "channel_plans": channel_plans}
