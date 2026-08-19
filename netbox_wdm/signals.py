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


def _pending_nodes(kind: str) -> set[int]:
    """Return the set of node pks awaiting `kind` work at the end of this transaction.

    The set lives on the database connection, so concurrent threads accumulate
    separately and each transaction starts from whatever the last flush left
    behind. A rolled back transaction never runs its callbacks, so its pks stay
    queued and are picked up by the next flush: the cost is a redundant rebuild,
    never a missed one.
    """
    connection = transaction.get_connection()
    store = getattr(connection, "_wdm_pending_nodes", None)
    if store is None:
        store = {}
        connection._wdm_pending_nodes = store
    return store.setdefault(kind, set())


def _drain(kind: str) -> list[int]:
    """Take every node pk queued for `kind`, leaving the queue empty."""
    pending = _pending_nodes(kind)
    node_pks = list(pending)
    pending.clear()
    return node_pks


def _rebuild_nodes(nodes: set[Any]) -> None:
    """Queue path rebuilds for a set of WdmNode instances, to run once on commit."""
    _pending_nodes("rebuild").update(node.pk for node in nodes if node.pk)
    transaction.on_commit(_flush_rebuilds)


def _flush_rebuilds() -> None:
    """Rebuild every node queued during this transaction, each exactly once.

    Every scheduling call registers this, so the first one to run does the work
    and the rest find an empty queue. Registering unconditionally keeps the
    queue and the callbacks from drifting apart when a transaction rolls back.
    """
    from .models import WdmNode
    from .trace import rebuild_wavelength_paths_for_node

    node_pks = _drain("rebuild")
    if not node_pks:
        return
    for node in WdmNode.objects.filter(pk__in=node_pks):
        rebuild_wavelength_paths_for_node(node)


def _recheck_port_sync(nodes: set[Any]) -> None:
    """Queue port sync hash recomputation for a set of WdmNode instances, to run once on commit."""
    _pending_nodes("port_sync").update(node.pk for node in nodes if node.pk)
    transaction.on_commit(_flush_port_sync)


def _flush_port_sync() -> None:
    """Recompute port sync state for every node queued during this transaction.

    Writes through queryset.update() rather than save() so the WdmNode post_save
    signal does not fire and schedule this work all over again.
    """
    from .models import WdmNode
    from .port_sync import check_port_sync, compute_expected_port_hash

    node_pks = _drain("port_sync")
    if not node_pks:
        return
    for node in WdmNode.objects.filter(pk__in=node_pks):
        WdmNode.objects.filter(pk=node.pk).update(
            expected_port_hash=compute_expected_port_hash(node),
            port_sync_valid=check_port_sync(node),
        )


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
