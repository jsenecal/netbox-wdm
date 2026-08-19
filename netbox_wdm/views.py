from __future__ import annotations

import json
from typing import Any

from dcim.models import DeviceType, FrontPort, ModuleType
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
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
    WdmLinePortPlanForm,
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
    WdmLinePortPlan,
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
    queryset = WdmProfile.objects.select_related("device_type", "module_type")

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        return {
            "line_port_plans": list(instance.line_port_plans.select_related("rear_port_template")),
        }


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


# ---- WdmLinePortPlan ----


@register_model_view(WdmLinePortPlan)
class WdmLinePortPlanView(generic.ObjectView):
    queryset = WdmLinePortPlan.objects.select_related("profile", "rear_port_template")


@register_model_view(WdmLinePortPlan, "edit")
class WdmLinePortPlanEditView(generic.ObjectEditView):
    queryset = WdmLinePortPlan.objects.select_related("profile", "rear_port_template")
    form = WdmLinePortPlanForm


@register_model_view(WdmLinePortPlan, "delete")
class WdmLinePortPlanDeleteView(generic.ObjectDeleteView):
    queryset = WdmLinePortPlan.objects.select_related("profile", "rear_port_template")


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
        module_ids: set[int] = set()
        include_unmoduled = False
        for ch in channels:
            if ch.mux_front_port_id:
                assigned_fp_ids.add(ch.mux_front_port_id)
            if ch.demux_front_port_id:
                assigned_fp_ids.add(ch.demux_front_port_id)
            if ch.module_id:
                module_ids.add(ch.module_id)
            else:
                include_unmoduled = True

        # Scope candidates to the module(s) actually represented among this node's
        # channels: a channel's mux/demux front port must belong to the same module
        # as the channel (or be module-less, for non-modular nodes). Without this,
        # front ports from unrelated modules on the same device would appear as
        # selectable options.
        module_scope = Q(module_id__in=module_ids) if module_ids else Q(pk__in=[])
        if include_unmoduled:
            module_scope |= Q(module__isnull=True)
        available_ports = (
            FrontPort.objects.filter(device=instance.device).filter(module_scope).exclude(pk__in=assigned_fp_ids)
        )

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


def _trace_cable_segment(
    from_node: Any, to_node: Any = None, from_module: Any = None, to_module: Any = None
) -> list[CableSegmentItem]:
    """Trace the full cable chain from a node's TX/BIDI rear port to the next WDM node.

    Follows through patch panels and intermediate devices, collecting every port and cable.
    When to_node is provided and from_node has multiple TX ports (e.g. ROADM),
    selects the TX port whose cable chain reaches to_node. from_module/to_module scope
    the line-port lookup and destination match to a single cassette module on a
    modular chassis (None means the device-level group).
    Returns a list of CableSegmentItem entries in order.
    """
    from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
    from django.contrib.contenttypes.models import ContentType

    from .models import WdmLinePort
    from .trace import get_max_trace_hops, warn_max_trace_hops_reached

    items: list[CableSegmentItem] = []
    rp_ct = ContentType.objects.get_for_model(RearPort)
    fp_ct = ContentType.objects.get_for_model(FrontPort)

    # Select the correct TX port — for multi-TX nodes (ROADM), pick the one reaching to_node
    tx_lps = list(
        WdmLinePort.objects.filter(wdm_node=from_node, module=from_module, role__in=["tx", "bidi"]).select_related(
            "rear_port"
        )
    )
    tx_lp = None
    if len(tx_lps) > 1 and to_node:
        from .trace import _get_far_end_node

        to_module_pk = to_module.pk if to_module else None
        for lp in tx_lps:
            if not lp.rear_port.cable_id:
                continue
            far_node, far_module, _ = _get_far_end_node(lp.rear_port)
            far_module_pk = far_module.pk if far_module else None
            if far_node and far_node.pk == to_node.pk and far_module_pk == to_module_pk:
                tx_lp = lp
                break
    if tx_lp is None:
        tx_lp = next((lp for lp in tx_lps if lp.rear_port.cable_id), None)
    if not tx_lp or not tx_lp.rear_port.cable_id:
        return items

    def _add_rp(rp: RearPort) -> None:
        items.append(
            CableSegmentItem(
                type="rear_port",
                id=rp.pk,
                name=rp.name,
                device=rp.device.name,
                url=rp.get_absolute_url(),
                color=rp.color or "",
            )
        )

    def _add_fp(fp: FrontPort) -> None:
        items.append(
            CableSegmentItem(
                type="front_port",
                id=fp.pk,
                name=fp.name,
                device=fp.device.name,
                url=fp.get_absolute_url(),
                color=fp.color or "",
            )
        )

    def _add_cable(cable: Cable) -> None:
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

    def _follow_cable_far_end(cable_id: int, local_id: int, local_ct: Any) -> tuple[Any | None, str]:
        """Find the far-end termination of a cable. Returns (object, type_str) or (None, '').

        Uses cable_end (A/B) to find the opposite side and position-index
        matching so that duplex/multi-strand cables follow the correct fibre.
        For simplex cables (1 termination per side) this reduces to the
        single far-end termination.
        """
        local_term = CableTermination.objects.filter(
            cable_id=cable_id, termination_type=local_ct, termination_id=local_id
        ).first()
        if not local_term:
            return None, ""

        far_end = "B" if local_term.cable_end == "A" else "A"

        # Determine position index of local port within its cable end
        same_end = list(
            CableTermination.objects.filter(cable_id=cable_id, cable_end=local_term.cable_end).order_by("pk")
        )
        local_idx = next((i for i, t in enumerate(same_end) if t.pk == local_term.pk), 0)

        far_terms = list(CableTermination.objects.filter(cable_id=cable_id, cable_end=far_end).order_by("pk"))

        def _resolve(ft: Any) -> tuple[Any | None, str]:
            if ft.termination_type == rp_ct:
                rp = RearPort.objects.filter(pk=ft.termination_id).select_related("device").first()
                if rp:
                    return rp, "rear_port"
            elif ft.termination_type == fp_ct:
                fp = FrontPort.objects.filter(pk=ft.termination_id).select_related("device").first()
                if fp:
                    return fp, "front_port"
            return None, ""

        # Position match (same index on the far end)
        if local_idx < len(far_terms):
            obj, typ = _resolve(far_terms[local_idx])
            if obj:
                return obj, typ

        # Fallback: first available on the far end
        for ft in far_terms:
            obj, typ = _resolve(ft)
            if obj:
                return obj, typ

        return None, ""

    # Start: source rear port
    source_rp = RearPort.objects.select_related("device").get(pk=tx_lp.rear_port_id)
    current_rp = source_rp
    _add_rp(current_rp)

    visited_ports: set[int] = {current_rp.pk}
    max_hops = get_max_trace_hops()
    for _hop in range(max_hops):
        fresh_rp = RearPort.objects.only("pk", "cable_id").get(pk=current_rp.pk)
        if not fresh_rp.cable_id:
            break

        cable = Cable.objects.get(pk=fresh_rp.cable_id)
        _add_cable(cable)

        far_obj, far_type = _follow_cable_far_end(fresh_rp.cable_id, fresh_rp.pk, rp_ct)
        if far_obj is None:
            break

        if far_type == "rear_port":
            _add_rp(far_obj)
            if far_obj.pk in visited_ports:
                break
            visited_ports.add(far_obj.pk)
            # Check if this is a WDM node — if so, we're done
            if WdmLinePort.objects.filter(rear_port=far_obj).exists():
                break
            # Intermediate device: follow PortMapping RP → FP, then FP's cable
            pm = PortMapping.objects.filter(rear_port=far_obj).select_related("front_port__device").first()
            if not pm or not pm.front_port.cable_id:
                break
            _add_fp(pm.front_port)
            exit_fp = pm.front_port
            exit_cable = Cable.objects.get(pk=exit_fp.cable_id)
            _add_cable(exit_cable)
            far2, far2_type = _follow_cable_far_end(exit_cable.pk, exit_fp.pk, fp_ct)
            if far2 is None:
                break
            if far2_type == "rear_port":
                _add_rp(far2)
                if far2.pk in visited_ports:
                    break
                visited_ports.add(far2.pk)
                if WdmLinePort.objects.filter(rear_port=far2).exists():
                    break
                current_rp = far2
                continue
            elif far2_type == "front_port":
                _add_fp(far2)
                pm2 = PortMapping.objects.filter(front_port=far2).select_related("rear_port__device").first()
                if pm2:
                    _add_rp(pm2.rear_port)
                    if pm2.rear_port.pk in visited_ports:
                        break
                    visited_ports.add(pm2.rear_port.pk)
                    current_rp = pm2.rear_port
                    continue
                break
        elif far_type == "front_port":
            _add_fp(far_obj)
            pm = PortMapping.objects.filter(front_port=far_obj).select_related("rear_port__device").first()
            if not pm:
                break
            _add_rp(pm.rear_port)
            if pm.rear_port.pk in visited_ports:
                break
            visited_ports.add(pm.rear_port.pk)
            if WdmLinePort.objects.filter(rear_port=pm.rear_port).exists():
                break
            current_rp = pm.rear_port
            continue

        break
    else:
        warn_max_trace_hops_reached(source_rp, max_hops)

    return items


def _build_trace_data_for_path(wl_path: Any, channel_id: int | None = None) -> ChannelTraceData:
    """Build ChannelTraceData for a WdmWavelengthPath, reusable by channel and circuit trace views."""
    elements = []
    for entry in wl_path.path_channels.select_related(
        "channel__wdm_node__device",
        "channel__mux_front_port",
        "channel__demux_front_port",
    ).order_by("sequence"):
        elements.append(path_element_from_channel(entry.channel, entry.sequence))

    cable_segments: list[CableSegment] = []
    hop_entries = list(
        wl_path.path_channels.select_related("channel__wdm_node__device", "channel__module").order_by("sequence")
    )
    for i in range(len(hop_entries) - 1):
        from_channel = hop_entries[i].channel
        to_channel = hop_entries[i + 1].channel
        from_node = from_channel.wdm_node
        to_node = to_channel.wdm_node
        items = _trace_cable_segment(from_node, to_node, from_channel.module, to_channel.module)
        cable_segments.append(
            CableSegment(
                from_sequence=hop_entries[i].sequence,
                to_sequence=hop_entries[i + 1].sequence,
                items=items,
            )
        )

    return ChannelTraceData(
        channel_id=channel_id or (elements[0].channel_id if elements else 0),
        wavelength_path_id=wl_path.pk,
        wavelength_nm=wl_path.wavelength_nm,
        grid_position=wl_path.grid_position,
        is_complete=wl_path.is_complete,
        is_active=wl_path.is_active,
        is_valid=wl_path.is_valid,
        elements=elements,
        cable_segments=cable_segments,
    )


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

        from .models import WdmWavelengthPathChannel

        path_entry = WdmWavelengthPathChannel.objects.filter(channel=instance).select_related("path").first()
        if not path_entry:
            return {"trace_data_list": [], "trace_data_list_json": "[]"}

        trace_data = _build_trace_data_for_path(path_entry.path, channel_id=instance.pk)
        return {
            "trace_data_list": [trace_data],
            "trace_data_list_json": json.dumps([asdict(trace_data)], cls=DjangoJSONEncoder),
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
    queryset = WdmCircuit.objects.select_related("tenant").prefetch_related("wavelength_paths")


@register_model_view(WdmCircuit, "trace", path="trace")
class WdmCircuitTraceView(generic.ObjectView):
    queryset = WdmCircuit.objects.select_related("tenant").prefetch_related("wavelength_paths")
    tab = ViewTab(
        label=_("Trace"),
        permission="netbox_wdm.view_wdmcircuit",
        weight=500,
    )

    def get_template_name(self) -> str:
        return "netbox_wdm/wdmcircuit_trace_tab.html"

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        from dataclasses import asdict

        paths = instance.wavelength_paths.all()
        if not paths.exists():
            return {"trace_data_list": [], "trace_data_list_json": "[]"}

        trace_data_list = [_build_trace_data_for_path(p) for p in paths]
        return {
            "trace_data_list": trace_data_list,
            "trace_data_list_json": json.dumps([asdict(td) for td in trace_data_list], cls=DjangoJSONEncoder),
        }


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


# ---- DeviceType / ModuleType WDM Profile Tabs ----


class WdmProfileTabViewMixin:
    """Shared extra-context lookup for the DeviceType and ModuleType WDM Profile tabs.

    Both tabs show the same profile summary, channel plans, and line port plans;
    only the anchor field (`device_type` vs `module_type`) they filter WdmProfile
    on differs.
    """

    profile_anchor_field: str

    def get_extra_context(self, request: Any, instance: Any) -> dict[str, Any]:
        profile = WdmProfile.objects.filter(**{self.profile_anchor_field: instance}).first()
        channel_plans = []
        line_port_plans = []
        if profile:
            channel_plans = list(
                profile.channel_plans.select_related("mux_front_port_template", "demux_front_port_template").order_by(
                    "grid_position"
                )
            )
            line_port_plans = list(profile.line_port_plans.select_related("rear_port_template"))
        return {"profile": profile, "channel_plans": channel_plans, "line_port_plans": line_port_plans}


@register_model_view(DeviceType, "wdm_profile", path="wdm-profile")
class DeviceTypeWdmProfileView(WdmProfileTabViewMixin, generic.ObjectView):
    queryset = DeviceType.objects.all()
    tab = ViewTab(
        label=_("WDM Profile"),
        visible=lambda obj: WdmProfile.objects.filter(device_type=obj).exists(),
        permission="netbox_wdm.view_wdmprofile",
        weight=1100,
    )
    profile_anchor_field = "device_type"

    def get_template_name(self) -> str:
        return "netbox_wdm/devicetype_wdm_tab.html"


@register_model_view(ModuleType, "wdm_profile", path="wdm-profile")
class ModuleTypeWdmProfileView(WdmProfileTabViewMixin, generic.ObjectView):
    queryset = ModuleType.objects.all()
    tab = ViewTab(
        label=_("WDM Profile"),
        visible=lambda obj: WdmProfile.objects.filter(module_type=obj).exists(),
        permission="netbox_wdm.view_wdmprofile",
        weight=1100,
    )
    profile_anchor_field = "module_type"

    def get_template_name(self) -> str:
        return "netbox_wdm/moduletype_wdm_tab.html"
