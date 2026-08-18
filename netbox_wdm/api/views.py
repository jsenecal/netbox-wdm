from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dcim.models import PortMapping, RearPort
from django.db import transaction
from django.db.models import Q
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from ..dataclasses import ChannelTraceData
from ..filters import (
    WdmChannelFilterSet,
    WdmChannelPlanFilterSet,
    WdmCircuitFilterSet,
    WdmLinePortFilterSet,
    WdmLinePortPlanFilterSet,
    WdmNodeFilterSet,
    WdmProfileFilterSet,
    WdmWavelengthPathFilterSet,
)
from ..models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmLinePortPlan,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
)
from .serializers import (
    WdmChannelPlanSerializer,
    WdmChannelSerializer,
    WdmCircuitSerializer,
    WdmLinePortPlanSerializer,
    WdmLinePortSerializer,
    WdmNodeSerializer,
    WdmProfileSerializer,
    WdmWavelengthPathSerializer,
)


class WdmProfileViewSet(NetBoxModelViewSet):
    queryset = WdmProfile.objects.select_related("device_type").prefetch_related("tags")
    serializer_class = WdmProfileSerializer
    filterset_class = WdmProfileFilterSet


class WdmChannelPlanViewSet(NetBoxModelViewSet):
    queryset = WdmChannelPlan.objects.select_related("profile").prefetch_related("tags")
    serializer_class = WdmChannelPlanSerializer
    filterset_class = WdmChannelPlanFilterSet


class WdmLinePortPlanViewSet(NetBoxModelViewSet):
    queryset = WdmLinePortPlan.objects.select_related("profile", "rear_port_template")
    serializer_class = WdmLinePortPlanSerializer
    filterset_class = WdmLinePortPlanFilterSet


def _apply_mapping(wdm_node: Any, desired_mapping: dict[int, dict[str, int | None]]) -> dict[str, int]:
    """Apply channel-to-port mapping changes. Uses bulk operations.

    desired_mapping format: { channel_pk: {"mux": port_id|None, "demux": port_id|None} }
    """
    channels = {ch.pk: ch for ch in wdm_node.channels.all()}
    line_ports = list(wdm_node.line_ports.select_related("rear_port").all())
    # Group line ports by module so create/delete only ever touch the rear ports of
    # the channel's own module (or the device-level group, for module=None). A
    # mixed chassis has independent line-port groups per module/cassette; writing
    # against every line port on the node cross-contaminates other groups' rear
    # ports with garbage PortMappings.
    line_ports_by_module: dict[int | None, list[Any]] = {}
    for lp in line_ports:
        line_ports_by_module.setdefault(lp.module_id, []).append(lp)

    added = removed = changed = 0
    channels_to_update = []
    old_fp_ids_to_delete = []
    new_mappings_to_create = []

    for ch_pk, ports in desired_mapping.items():
        ch = channels.get(ch_pk)
        if ch is None:
            continue

        module_line_ports = line_ports_by_module.get(ch.module_id, [])

        desired_mux = ports.get("mux")
        desired_demux = ports.get("demux")
        current_mux = ch.mux_front_port_id
        current_demux = ch.demux_front_port_id

        if current_mux == desired_mux and current_demux == desired_demux:
            continue

        for current_fp_pk in (current_mux, current_demux):
            if current_fp_pk is not None:
                old_fp_ids_to_delete.append((current_fp_pk, ch.grid_position, module_line_ports))

        for desired_fp_pk in (desired_mux, desired_demux):
            if desired_fp_pk is not None:
                for tp in module_line_ports:
                    new_mappings_to_create.append(
                        PortMapping(
                            device=wdm_node.device,
                            front_port_id=desired_fp_pk,
                            rear_port=tp.rear_port,
                            front_port_position=1,
                            rear_port_position=ch.grid_position,
                        )
                    )

        ch.mux_front_port_id = desired_mux
        ch.demux_front_port_id = desired_demux
        channels_to_update.append(ch)

        had_port = current_mux is not None or current_demux is not None
        has_port = desired_mux is not None or desired_demux is not None
        if not had_port and has_port:
            added += 1
        elif had_port and not has_port:
            removed += 1
        else:
            changed += 1

    if channels_to_update:
        WdmChannel.objects.bulk_update(channels_to_update, ["mux_front_port_id", "demux_front_port_id"])

    if old_fp_ids_to_delete:
        delete_q = Q()
        for fp_id, grid_pos, module_line_ports in old_fp_ids_to_delete:
            for tp in module_line_ports:
                delete_q |= Q(front_port_id=fp_id, rear_port=tp.rear_port, rear_port_position=grid_pos)
        if delete_q:
            PortMapping.objects.filter(delete_q).delete()

    if new_mappings_to_create:
        PortMapping.objects.bulk_create(new_mappings_to_create)

    if channels_to_update:
        _retrace_affected_paths(wdm_node, line_ports)

    return {"added": added, "removed": removed, "changed": changed}


def _retrace_affected_paths(wdm_node: Any, line_ports: list[Any]) -> None:
    """Retrace CablePaths that traverse cables connected to the node's line ports."""
    from dcim.models import CablePath, CableTermination
    from django.contrib.contenttypes.models import ContentType

    rp_ids = [tp.rear_port_id for tp in line_ports]
    if not rp_ids:
        return

    rp_ct = ContentType.objects.get_for_model(RearPort)
    cable_ids = (
        CableTermination.objects.filter(termination_type=rp_ct, termination_id__in=rp_ids)
        .values_list("cable_id", flat=True)
        .distinct()
    )

    if not cable_ids:
        return

    q = Q()
    for cid in cable_ids:
        q |= Q(_nodes__contains=[{"cable_id": cid}])
    affected_paths = CablePath.objects.filter(q).distinct()
    for path in affected_paths:
        path.retrace()


class WdmNodeViewSet(NetBoxModelViewSet):
    queryset = WdmNode.objects.select_related("device").prefetch_related("tags")
    serializer_class = WdmNodeSerializer
    filterset_class = WdmNodeFilterSet

    @action(detail=True, methods=["post"], url_path="apply-mapping")
    def apply_mapping(self, request: Any, pk: int | None = None) -> Response:
        """Apply channel-to-port mapping changes atomically."""
        node = self.get_object()

        last_updated = request.data.get("last_updated")
        if last_updated and str(node.last_updated) != last_updated:
            return Response(
                {"detail": "Node was modified since editor loaded. Please reload."},
                status=status.HTTP_409_CONFLICT,
            )

        raw_mapping = request.data.get("mapping", {})
        desired = {}
        for k, v in raw_mapping.items():
            ch_pk = int(k)
            if isinstance(v, dict):
                desired[ch_pk] = {
                    "mux": int(v["mux"]) if v.get("mux") else None,
                    "demux": int(v["demux"]) if v.get("demux") else None,
                }
            else:
                # Legacy format: single port ID maps to mux only
                desired[ch_pk] = {"mux": int(v) if v else None, "demux": None}

        with transaction.atomic():
            errors = node.validate_channel_mapping(desired)
            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            result = _apply_mapping(node, desired)

        node.refresh_from_db()
        result["last_updated"] = str(node.last_updated)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="sync-ports")
    def sync_ports(self, request: Any, pk: int | None = None) -> Response:
        """Sync port mappings to match the WDM channel grid.

        Default is dry run. Pass ?dry_run=false to apply changes.
        """
        from ..port_sync import apply_sync, compute_sync_diff

        node = self.get_object()
        dry_run = request.query_params.get("dry_run", "true").lower() != "false"

        if dry_run:
            diff = compute_sync_diff(node)
            return Response({"port_sync_valid": node.port_sync_valid, "dry_run": True, **diff})

        with transaction.atomic():
            result = apply_sync(node)

        node.refresh_from_db()
        return Response({"port_sync_valid": node.port_sync_valid, "dry_run": False, **result})


class WdmLinePortViewSet(NetBoxModelViewSet):
    queryset = WdmLinePort.objects.select_related("wdm_node", "rear_port").prefetch_related("tags")
    serializer_class = WdmLinePortSerializer
    filterset_class = WdmLinePortFilterSet


class WdmChannelViewSet(NetBoxModelViewSet):
    queryset = WdmChannel.objects.select_related("wdm_node").prefetch_related("tags")
    serializer_class = WdmChannelSerializer
    filterset_class = WdmChannelFilterSet

    @action(detail=True, methods=["get"], url_path="trace")
    def trace(self, request: Any, pk: int | None = None) -> Response:
        """Return the full wavelength path trace for this channel.

        Delegates segment building to views._build_trace_data_for_path, which
        (via _trace_cable_segment) scopes the TX/BIDI line-port lookup to each
        hop channel's module and picks the port whose cable chain actually
        reaches the next hop's node/module -- instead of an arbitrary
        module- and destination-blind ``.first()``.
        """
        from ..models import WdmWavelengthPathChannel
        from ..views import _build_trace_data_for_path

        channel = self.get_object()

        # Find wavelength path this channel belongs to
        path_entry = WdmWavelengthPathChannel.objects.filter(channel=channel).select_related("path").first()

        if not path_entry:
            return Response(
                asdict(
                    ChannelTraceData(
                        channel_id=channel.pk,
                        wavelength_path_id=None,
                        wavelength_nm=None,
                        grid_position=channel.grid_position,
                        is_complete=False,
                        is_active=False,
                        is_valid=False,
                    )
                )
            )

        trace_data = _build_trace_data_for_path(path_entry.path, channel_id=channel.pk)
        return Response(asdict(trace_data))


class WdmWavelengthPathViewSet(NetBoxModelViewSet):
    queryset = WdmWavelengthPath.objects.prefetch_related("tags")
    serializer_class = WdmWavelengthPathSerializer
    filterset_class = WdmWavelengthPathFilterSet


class WdmCircuitViewSet(NetBoxModelViewSet):
    queryset = WdmCircuit.objects.select_related("tenant").prefetch_related("tags", "wavelength_paths")
    serializer_class = WdmCircuitSerializer
    filterset_class = WdmCircuitFilterSet

    @action(detail=True, methods=["get"], url_path="stitch")
    def stitch(self, request: Any, pk: int | None = None) -> Response:
        """Return the stitched end-to-end wavelength paths."""
        circuit = self.get_object()
        stitched = circuit.get_stitched_paths()
        return Response(
            {
                "service_id": circuit.pk,
                "service_name": circuit.name,
                "status": circuit.status,
                "paths": [
                    {
                        "wavelength_path_id": wp.pk,
                        "wavelength_nm": wp.wavelength_nm,
                        "is_complete": wp.is_complete,
                        "is_active": wp.is_active,
                        "elements": [asdict(e) for e in elements],
                    }
                    for wp, elements in stitched
                ],
            }
        )
