from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save


def _device_post_save(sender: type, instance: Any, created: bool, **kwargs: Any) -> None:
    """Auto-create WdmNode when a Device is created from a DeviceType with a WDM profile."""
    if not created:
        return

    from .models import WdmNode, WdmProfile

    try:
        profile = WdmProfile.objects.get(device_type=instance.device_type)
    except WdmProfile.DoesNotExist:
        return

    def _create_node() -> None:
        if WdmNode.objects.filter(device=instance).exists():
            return
        WdmNode.objects.create(
            device=instance,
            node_type=profile.node_type,
            grid=profile.grid,
        )

    transaction.on_commit(_create_node)


def _rebuild_nodes(nodes: set[Any]) -> None:
    """Schedule path rebuilds for a set of WdmNode instances on transaction commit."""
    from .trace import rebuild_wavelength_paths_for_node

    for node in nodes:
        transaction.on_commit(lambda n=node: rebuild_wavelength_paths_for_node(n))


def _cable_trace_paths(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths for WDM nodes connected via this cable's rear port terminations."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    from .models import WdmLinePort

    cable = instance
    rp_ct = ContentType.objects.get_for_model(RearPort)
    rp_ids = list(
        CableTermination.objects.filter(cable=cable, termination_type=rp_ct).values_list("termination_id", flat=True)
    )
    if not rp_ids:
        return

    nodes = set()
    for lp in WdmLinePort.objects.filter(rear_port_id__in=rp_ids).select_related("wdm_node"):
        nodes.add(lp.wdm_node)

    if nodes:
        _rebuild_nodes(nodes)


def _cable_post_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild paths for all nodes that had paths — terminations are already gone after delete."""
    from .models import WdmWavelengthPath, WdmWavelengthPathChannel

    node_pks = (
        WdmWavelengthPathChannel.objects.filter(path__in=WdmWavelengthPath.objects.all())
        .values_list("channel__wdm_node", flat=True)
        .distinct()
    )

    from .models import WdmNode

    nodes = set(WdmNode.objects.filter(pk__in=node_pks))
    if nodes:
        _rebuild_nodes(nodes)


def _channel_post_save(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths when a channel is created or updated."""
    _rebuild_nodes({instance.wdm_node})


def _channel_post_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths when a channel is deleted."""
    _rebuild_nodes({instance.wdm_node})


def _lineport_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths when a line port changes."""
    _rebuild_nodes({instance.wdm_node})


def _portmapping_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths when a port mapping changes."""
    from .models import WdmNode

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    _rebuild_nodes({node})


def connect_signals() -> None:
    """Connect device signals. Called from AppConfig.ready()."""
    from dcim.models import Cable, Device, PortMapping
    from dcim.models.cables import trace_paths

    from .models import WdmChannel, WdmLinePort

    post_save.connect(_device_post_save, sender=Device, dispatch_uid="wdm_device_post_save")
    trace_paths.connect(_cable_trace_paths, sender=Cable, dispatch_uid="wdm_cable_trace_paths")
    post_delete.connect(_cable_post_delete, sender=Cable, dispatch_uid="wdm_cable_post_delete")
    post_save.connect(_channel_post_save, sender=WdmChannel, dispatch_uid="wdm_channel_post_save")
    post_delete.connect(_channel_post_delete, sender=WdmChannel, dispatch_uid="wdm_channel_post_delete")
    post_save.connect(_lineport_changed, sender=WdmLinePort, dispatch_uid="wdm_lineport_post_save")
    post_delete.connect(_lineport_changed, sender=WdmLinePort, dispatch_uid="wdm_lineport_post_delete")
    post_save.connect(_portmapping_changed, sender=PortMapping, dispatch_uid="wdm_portmapping_post_save")
    post_delete.connect(_portmapping_changed, sender=PortMapping, dispatch_uid="wdm_portmapping_post_delete")
