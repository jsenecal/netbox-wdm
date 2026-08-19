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


def _pass_through_port_kinds() -> dict[int, str]:
    """Map the FrontPort and RearPort content type ids to walkable port kinds."""
    from dcim.models import FrontPort, RearPort
    from django.contrib.contenttypes.models import ContentType

    return {
        ContentType.objects.get_for_model(FrontPort).pk: "front",
        ContentType.objects.get_for_model(RearPort).pk: "rear",
    }


def _wdm_nodes_reachable_from_cable(cable: Any) -> set[Any]:
    """Find WDM nodes whose line ports are reachable from a cable's pass-through terminations.

    A cable that lands directly on a WDM line port is trivially attributable, but
    a mid-span trunk between two patch panels terminates only pass-through ports.
    Walk outward from every front/rear port termination -- crossing pass-through
    devices via their port mappings and following the cables hanging off them --
    until rear ports registered as WDM line ports are reached. Line ports bound
    the walk: it never descends into a WDM device's internals.
    """
    from collections import deque

    from dcim.models import CableTermination, FrontPort, PortMapping, RearPort

    from .models import WdmLinePort, WdmNode

    kinds = _pass_through_port_kinds()

    queue: deque[tuple[str, int]] = deque()
    for ct_id, term_id in CableTermination.objects.filter(cable=cable).values_list(
        "termination_type_id", "termination_id"
    ):
        if ct_id in kinds:
            queue.append((kinds[ct_id], term_id))

    node_pks: set[int] = set()
    visited: set[tuple[str, int]] = set()
    while queue:
        kind, pk = queue.popleft()
        if (kind, pk) in visited:
            continue
        visited.add((kind, pk))

        if kind == "rear":
            wdm_node_id = WdmLinePort.objects.filter(rear_port_id=pk).values_list("wdm_node_id", flat=True).first()
            if wdm_node_id is not None:
                node_pks.add(wdm_node_id)
                continue
            mapped = PortMapping.objects.filter(rear_port_id=pk).values_list("front_port_id", flat=True)
            queue.extend(("front", fp_id) for fp_id in mapped)
            port = RearPort.objects.only("pk", "cable", "cable_end").filter(pk=pk).first()
        else:
            mapped = PortMapping.objects.filter(front_port_id=pk).values_list("rear_port_id", flat=True)
            queue.extend(("rear", rp_id) for rp_id in mapped)
            port = FrontPort.objects.only("pk", "cable", "cable_end").filter(pk=pk).first()

        if port is None or not port.cable_id:
            continue
        far_terminations = CableTermination.objects.filter(cable_id=port.cable_id).exclude(cable_end=port.cable_end)
        for ct_id, term_id in far_terminations.values_list("termination_type_id", "termination_id"):
            if ct_id in kinds:
                queue.append((kinds[ct_id], term_id))

    return set(WdmNode.objects.filter(pk__in=node_pks))


def _cable_trace_paths(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild wavelength paths for WDM nodes reachable from this cable's terminations."""
    nodes = _wdm_nodes_reachable_from_cable(instance)
    if nodes:
        _rebuild_nodes(nodes)


def _cable_pre_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Capture which WDM nodes have cable paths traversing this cable, before it is deleted.

    Core NetBox retraces every affected CablePath in its own Cable post_delete
    receiver, which runs before this plugin's; by the time our post_delete
    handler fires, the deleted cable no longer appears in any CablePath's
    flattened node list. Query here, while the rows still reference the cable,
    map the paths' rear ports to WDM line ports, and stash the result on the
    instance for _cable_post_delete.
    """
    from dcim.models import CablePath, RearPort
    from django.contrib.contenttypes.models import ContentType

    from .models import WdmLinePort

    rp_ct_id = ContentType.objects.get_for_model(RearPort).pk

    matched = False
    rear_port_ids: set[int] = set()
    for path in CablePath.objects.filter(_nodes__contains=instance):
        matched = True
        for node in path._nodes:
            ct_id, _, object_id = node.partition(":")
            if int(ct_id) == rp_ct_id:
                rear_port_ids.add(int(object_id))

    node_pks: set[int] = set()
    if rear_port_ids:
        node_pks = set(WdmLinePort.objects.filter(rear_port_id__in=rear_port_ids).values_list("wdm_node_id", flat=True))

    instance._wdm_cablepath_matched = matched
    instance._wdm_affected_node_pks = node_pks


def _cable_post_clean(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reject role-incompatible WDM trunk terminations while a cable is being validated.

    Raised from the post_clean signal, which fires wherever full_clean() runs
    (forms, REST API). A bare .save() in a script bypasses clean() entirely, so
    the port-sync flagging machinery stays in place as a backstop: this handler
    is prevention on the common path, not a replacement for detection.

    Duplex (multi-terminated) cables pair fibres by position index --
    a_terminations[i] carries the same fibre as b_terminations[i] -- so roles
    are compared per index pair. When one end has a single termination it is
    compared against every termination on the other end. Ends with differing
    multi-termination counts have no defined fibre pairing, so they are left
    alone. Only terminations that are WdmLinePort-managed rear ports are
    inspected; every other termination passes through untouched.
    """
    from dcim.models import RearPort
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext as _

    from .choices import WdmLineRoleChoices
    from .models import WdmLinePort

    a_terms = list(instance.a_terminations)
    b_terms = list(instance.b_terminations)

    rp_ids = {t.pk for t in a_terms + b_terms if isinstance(t, RearPort) and t.pk}
    if not rp_ids:
        return
    roles = dict(WdmLinePort.objects.filter(rear_port_id__in=rp_ids).values_list("rear_port_id", "role"))
    if not roles:
        return

    if len(a_terms) == len(b_terms):
        pairs = zip(a_terms, b_terms, strict=True)
    elif len(a_terms) == 1:
        pairs = ((a_terms[0], b) for b in b_terms)
    elif len(b_terms) == 1:
        pairs = ((a, b_terms[0]) for a in a_terms)
    else:
        return

    for term_a, term_b in pairs:
        if not (isinstance(term_a, RearPort) and isinstance(term_b, RearPort)):
            continue
        role_a = roles.get(term_a.pk)
        role_b = roles.get(term_b.pk)
        if role_a is None or role_b is None:
            continue
        if role_a == role_b and role_a in (WdmLineRoleChoices.TX, WdmLineRoleChoices.RX):
            raise ValidationError(
                _(
                    "Invalid WDM trunk cabling: {port_a} and {port_b} are both {role} line ports. "
                    "Connect TX to RX (or use bidirectional line ports)."
                ).format(
                    port_a=term_a,
                    port_b=term_b,
                    role=role_a.upper(),
                )
            )


def _cable_post_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Rebuild paths for the WDM nodes whose cable paths crossed the deleted cable.

    Uses the node set captured by _cable_pre_delete. CablePath rows only exist
    where a path endpoint (e.g. a client interface) is cabled at the edge, so a
    dark trunk -- provisioned channels with nothing lit -- matches no CablePath
    at all and cannot be scoped; fall back to rebuilding every node that
    participates in any wavelength path, as before.
    """
    from .models import WdmNode

    if getattr(instance, "_wdm_cablepath_matched", False):
        nodes = set(WdmNode.objects.filter(pk__in=instance._wdm_affected_node_pks))
        if nodes:
            _rebuild_nodes(nodes)
        return

    from .models import WdmWavelengthPathChannel

    node_pks = WdmWavelengthPathChannel.objects.values_list("channel__wdm_node", flat=True).distinct()
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
    from netbox.signals import post_clean

    from .models import WdmChannel, WdmLinePort

    post_save.connect(_device_post_save, sender=Device, dispatch_uid="wdm_device_post_save")
    post_clean.connect(_cable_post_clean, sender=Cable, dispatch_uid="wdm_cable_post_clean")
    trace_paths.connect(_cable_trace_paths, sender=Cable, dispatch_uid="wdm_cable_trace_paths")
    pre_delete.connect(_cable_pre_delete, sender=Cable, dispatch_uid="wdm_cable_pre_delete")
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
