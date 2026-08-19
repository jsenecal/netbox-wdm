from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete


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
    from .models import WdmNode

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


def _module_post_save(sender: type, instance: Any, created: bool, **kwargs: Any) -> None:
    """Populate channels and line ports when a profiled module is installed into a WDM node's device."""
    if not created:
        return

    from .models import WdmNode

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    transaction.on_commit(lambda: node.populate_module(instance))


def _cleanup_after_module_delete(nodes: set[Any], affected_path_ids: set[int]) -> None:
    """Prune broken wavelength paths and retrace affected nodes after a module's rows cascade away.

    Runs after the module (and its channels, line ports, and wavelength-path
    entries) have already been deleted via plain FK cascades. A path that lost
    some but not all of its channels is left partial (fewer than 2 entries) and
    no longer means anything, so it and any leftover entries are dropped here;
    surviving nodes are then retraced and rechecked for port sync.
    """
    from .models import WdmWavelengthPath

    for path in WdmWavelengthPath.objects.filter(pk__in=affected_path_ids):
        if path.path_channels.count() < 2:
            path.path_channels.all().delete()
            path.delete()

    _rebuild_nodes(nodes)
    _recheck_port_sync(nodes)


def _module_pre_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Capture WDM nodes affected by a module's removal, then schedule cleanup for after it cascades.

    Deleting the module cascades (plain FK on_delete=CASCADE) through its
    WdmChannel and WdmLinePort rows, and further through any WdmWavelengthPathChannel
    entries referencing those channels -- wavelength paths are derived data, not
    source of truth, so none of that needs protecting. This handler only captures,
    before the cascade runs, which nodes are affected (the module's own node, plus
    any far-end node sharing a wavelength path with one of the module's channels)
    and which paths those channels belonged to, then defers the actual pruning and
    retrace to `_cleanup_after_module_delete` once the transaction commits (i.e.
    once the cascade has already happened).
    """
    from .models import WdmChannel, WdmNode, WdmWavelengthPathChannel

    try:
        node = WdmNode.objects.get(device=instance.device)
    except WdmNode.DoesNotExist:
        return

    channel_ids = list(WdmChannel.objects.filter(module=instance).values_list("pk", flat=True))
    nodes = {node}
    affected_path_ids: set[int] = set()

    if channel_ids:
        entries = WdmWavelengthPathChannel.objects.filter(channel_id__in=channel_ids)
        affected_path_ids = set(entries.values_list("path_id", flat=True))
        if affected_path_ids:
            far_node_pks = (
                WdmWavelengthPathChannel.objects.filter(path_id__in=affected_path_ids)
                .exclude(channel_id__in=channel_ids)
                .values_list("channel__wdm_node", flat=True)
                .distinct()
            )
            nodes |= set(WdmNode.objects.filter(pk__in=far_node_pks))

    transaction.on_commit(lambda: _cleanup_after_module_delete(nodes, affected_path_ids))


def connect_signals() -> None:
    """Connect device signals. Called from AppConfig.ready()."""
    from dcim.models import Cable, Device, FrontPort, Module, PortMapping, RearPort
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
    post_save.connect(_module_post_save, sender=Module, dispatch_uid="wdm_module_post_save")
    pre_delete.connect(_module_pre_delete, sender=Module, dispatch_uid="wdm_module_pre_delete")
