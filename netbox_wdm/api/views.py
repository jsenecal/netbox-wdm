from dcim.models import PortMapping, RearPort
from django.db import transaction
from django.db.models import Q
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from ..filters import (
    WavelengthChannelFilterSet,
    WavelengthServiceFilterSet,
    WdmChannelTemplateFilterSet,
    WdmDeviceTypeProfileFilterSet,
    WdmNodeFilterSet,
    WdmTrunkPortFilterSet,
)
from ..models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)
from .serializers import (
    WavelengthChannelSerializer,
    WavelengthServiceSerializer,
    WdmChannelTemplateSerializer,
    WdmDeviceTypeProfileSerializer,
    WdmNodeSerializer,
    WdmTrunkPortSerializer,
)


class WdmDeviceTypeProfileViewSet(NetBoxModelViewSet):
    queryset = WdmDeviceTypeProfile.objects.prefetch_related("device_type", "tags")
    serializer_class = WdmDeviceTypeProfileSerializer
    filterset_class = WdmDeviceTypeProfileFilterSet


class WdmChannelTemplateViewSet(NetBoxModelViewSet):
    queryset = WdmChannelTemplate.objects.prefetch_related("profile", "tags")
    serializer_class = WdmChannelTemplateSerializer
    filterset_class = WdmChannelTemplateFilterSet


def _apply_mapping(wdm_node, desired_mapping: dict[int, int | None]) -> dict:
    """Apply channel-to-port mapping changes. Uses bulk operations."""
    channels = {ch.pk: ch for ch in wdm_node.channels.all()}
    trunk_ports = list(wdm_node.trunk_ports.select_related("rear_port").all())

    added = removed = changed = 0
    channels_to_update = []
    old_fp_ids_to_delete = []
    new_mappings_to_create = []

    for ch_pk, desired_fp_pk in desired_mapping.items():
        ch = channels.get(ch_pk)
        if ch is None:
            continue

        current_fp_pk = ch.front_port_id
        if current_fp_pk == desired_fp_pk:
            continue

        if current_fp_pk is not None:
            old_fp_ids_to_delete.append((current_fp_pk, ch.grid_position))

        if desired_fp_pk is not None:
            for tp in trunk_ports:
                new_mappings_to_create.append(
                    PortMapping(
                        device=wdm_node.device,
                        front_port_id=desired_fp_pk,
                        rear_port=tp.rear_port,
                        front_port_position=1,
                        rear_port_position=ch.grid_position,
                    )
                )

        ch.front_port_id = desired_fp_pk
        channels_to_update.append(ch)

        if current_fp_pk is None and desired_fp_pk is not None:
            added += 1
        elif current_fp_pk is not None and desired_fp_pk is None:
            removed += 1
        else:
            changed += 1

    if channels_to_update:
        WavelengthChannel.objects.bulk_update(channels_to_update, ["front_port_id"])

    if old_fp_ids_to_delete:
        delete_q = Q()
        for fp_id, grid_pos in old_fp_ids_to_delete:
            for tp in trunk_ports:
                delete_q |= Q(front_port_id=fp_id, rear_port=tp.rear_port, rear_port_position=grid_pos)
        if delete_q:
            PortMapping.objects.filter(delete_q).delete()

    if new_mappings_to_create:
        PortMapping.objects.bulk_create(new_mappings_to_create)

    if channels_to_update:
        _retrace_affected_paths(wdm_node, trunk_ports)

    return {"added": added, "removed": removed, "changed": changed}


def _retrace_affected_paths(wdm_node, trunk_ports):
    """Retrace CablePaths that traverse cables connected to the node's trunk ports."""
    from dcim.models import CablePath, CableTermination
    from django.contrib.contenttypes.models import ContentType

    rp_ids = [tp.rear_port_id for tp in trunk_ports]
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
    queryset = WdmNode.objects.prefetch_related("device", "tags")
    serializer_class = WdmNodeSerializer
    filterset_class = WdmNodeFilterSet

    @action(detail=True, methods=["post"], url_path="apply-mapping")
    def apply_mapping(self, request, pk=None):
        """Apply channel-to-port mapping changes atomically."""
        node = self.get_object()

        last_updated = request.data.get("last_updated")
        if last_updated and str(node.last_updated) != last_updated:
            return Response(
                {"detail": "Node was modified since editor loaded. Please reload."},
                status=status.HTTP_409_CONFLICT,
            )

        desired = request.data.get("mapping", {})
        desired = {int(k): (int(v) if v else None) for k, v in desired.items()}

        with transaction.atomic():
            errors = WdmNode.validate_channel_mapping(node, desired)
            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            result = _apply_mapping(node, desired)

        node.refresh_from_db()
        result["last_updated"] = str(node.last_updated)
        return Response(result)


class WdmTrunkPortViewSet(NetBoxModelViewSet):
    queryset = WdmTrunkPort.objects.prefetch_related("wdm_node", "rear_port", "tags")
    serializer_class = WdmTrunkPortSerializer
    filterset_class = WdmTrunkPortFilterSet


class WavelengthChannelViewSet(NetBoxModelViewSet):
    queryset = WavelengthChannel.objects.prefetch_related("wdm_node", "tags")
    serializer_class = WavelengthChannelSerializer
    filterset_class = WavelengthChannelFilterSet


class WavelengthServiceViewSet(NetBoxModelViewSet):
    queryset = WavelengthService.objects.prefetch_related("tenant", "tags")
    serializer_class = WavelengthServiceSerializer
    filterset_class = WavelengthServiceFilterSet

    @action(detail=True, methods=["get"], url_path="stitch")
    def stitch(self, request, pk=None):
        """Return the stitched end-to-end wavelength path."""
        service = self.get_object()
        path = service.get_stitched_path()
        return Response(
            {
                "service_id": service.pk,
                "service_name": service.name,
                "wavelength_nm": float(service.wavelength_nm),
                "status": service.status,
                "is_complete": len(path) > 0,
                "hops": path,
            }
        )
