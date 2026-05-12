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


def _recheck_port_sync(nodes: set[Any]) -> None:
    """Schedule port sync hash recomputation for a set of WdmNode instances on transaction commit.

    Uses WdmNode.objects.filter(pk=n.pk).update(...) to avoid triggering the WdmNode
    post_save signal (which would cause infinite recursion).
    """
    from .models import WdmNode
    from .port_sync import check_port_sync, compute_expected_port_hash

    for node in nodes:

        def _do_recheck(n: Any = node) -> None:
            try:
                fresh = WdmNode.objects.get(pk=n.pk)
            except WdmNode.DoesNotExist:
                return
            expected_hash = compute_expected_port_hash(fresh)
            in_sync = check_port_sync(fresh)
            WdmNode.objects.filter(pk=fresh.pk).update(
                expected_port_hash=expected_hash,
                port_sync_valid=in_sync,
            )

        transaction.on_commit(_do_recheck)


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


def _channel_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths and recheck port sync when a channel is created, updated, or deleted."""
    nodes = {instance.wdm_node}
    _rebuild_nodes(nodes)
    _recheck_port_sync(nodes)


def _lineport_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths and recheck port sync when a line port changes."""
    nodes = {instance.wdm_node}
    _rebuild_nodes(nodes)
    _recheck_port_sync(nodes)


def _portmapping_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths and recheck port sync when a port mapping changes."""
    from dcim.models import PortMapping

    from .models import WdmNode

    # NetBox's FrontPortFormMixin._save_m2m sends post_save with sender=PortMapping
    # even when the instance is a PortTemplateMapping (DeviceType-level template).
    # Templates have no live device, so there is nothing for us to rebuild.
    if not isinstance(instance, PortMapping):
        return

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    nodes = {node}
    _rebuild_nodes(nodes)
    _recheck_port_sync(nodes)


def _frontport_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Recheck port sync when a FrontPort is created, updated, or deleted."""
    from .models import WdmNode

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    _recheck_port_sync({node})


def _rearport_changed(sender: type, instance: Any, **kwargs: Any) -> None:
    """Recheck port sync when a RearPort is created, updated, or deleted."""
    from .models import WdmNode

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    _recheck_port_sync({node})


def connect_signals() -> None:
    """Connect device signals. Called from AppConfig.ready()."""
    from dcim.models import Cable, Device, FrontPort, PortMapping, RearPort
    from dcim.models.cables import trace_paths

    from .models import WdmChannel, WdmLinePort

    post_save.connect(_device_post_save, sender=Device, dispatch_uid="wdm_device_post_save")
    trace_paths.connect(_cable_trace_paths, sender=Cable, dispatch_uid="wdm_cable_trace_paths")
    post_delete.connect(_cable_post_delete, sender=Cable, dispatch_uid="wdm_cable_post_delete")
    post_save.connect(_channel_changed, sender=WdmChannel, dispatch_uid="wdm_channel_post_save")
    post_delete.connect(_channel_changed, sender=WdmChannel, dispatch_uid="wdm_channel_post_delete")
    post_save.connect(_lineport_changed, sender=WdmLinePort, dispatch_uid="wdm_lineport_post_save")
    post_delete.connect(_lineport_changed, sender=WdmLinePort, dispatch_uid="wdm_lineport_post_delete")
    post_save.connect(_portmapping_changed, sender=PortMapping, dispatch_uid="wdm_portmapping_post_save")
    post_delete.connect(_portmapping_changed, sender=PortMapping, dispatch_uid="wdm_portmapping_post_delete")
    post_save.connect(_frontport_changed, sender=FrontPort, dispatch_uid="wdm_frontport_post_save")
    post_delete.connect(_frontport_changed, sender=FrontPort, dispatch_uid="wdm_frontport_post_delete")
    post_save.connect(_rearport_changed, sender=RearPort, dispatch_uid="wdm_rearport_post_save")
    post_delete.connect(_rearport_changed, sender=RearPort, dispatch_uid="wdm_rearport_post_delete")
