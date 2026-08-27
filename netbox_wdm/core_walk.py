"""Cable-chain traversal delegated to NetBox's own CablePath walker.

``CablePath.from_origin`` already understands every cabling permutation this
plugin cares about: a patch panel entered or left at either face, panels
cascaded rear-to-front, and the A-to-Z hop across a carrier circuit, which
joins two halves of a fibre run with no cable of its own. It resolves each
cable's strand pairing through the cable profile, so duplex trunks follow
the intended fibre. Delegating to it leaves one traversal engine to
maintain instead of the plugin's own.

The walk is invoked ephemerally and its result is never written to core's
``CablePath`` table: core's signal handlers retrace or delete every row
whose ``_nodes`` match a changed cable, so a plugin-created row would not
survive its own port mappings being rebuilt.

Core's walker carries no visited set and no hop bound -- a cabling loop
spins forever, and these walks run inside signal handlers where that would
hang a worker. Every walk is therefore preceded by a structural pre-scan
that proves the chain terminates before core is asked to trace it.
"""

from __future__ import annotations

import logging
from typing import Any

from circuits.models import CircuitTermination
from dcim.models import CablePath, FrontPort, PortMapping, RearPort
from netbox.plugins import get_plugin_config

logger = logging.getLogger(__name__)

DEFAULT_MAX_TRACE_HOPS = 100


def get_max_trace_hops() -> int:
    """Return the cable-segment cap for chain walks (max_trace_hops plugin setting)."""
    return get_plugin_config("netbox_wdm", "max_trace_hops", DEFAULT_MAX_TRACE_HOPS)


def _key(obj: Any) -> tuple[str, int]:
    return (obj._meta.label_lower, obj.pk)


def _cross_all(peers: list[Any]) -> list[Any]:
    """Return the ports a whole level of the chain continues from.

    A front port hands off to the rear ports it maps to (and the reverse);
    a circuit termination hands off to the other termination of the same
    circuit. Anything else terminates the chain. Each kind is resolved in
    one query for the entire level rather than one per port.

    Dark ports are dropped: with no cable they cannot carry the chain
    further, and skipping them avoids a fruitless ``link_peers`` lookup
    each. A mux's channel front ports are the common case -- a walk that
    reaches the far trunk crosses into all of them and none is cabled.
    """
    front_ports, rear_ports, terminations = [], [], []
    for peer in peers:
        if isinstance(peer, FrontPort):
            front_ports.append(peer)
        elif isinstance(peer, RearPort):
            rear_ports.append(peer)
        elif isinstance(peer, CircuitTermination):
            terminations.append(peer)

    onward: list[Any] = []
    if front_ports:
        onward += [
            pm.rear_port for pm in PortMapping.objects.filter(front_port__in=front_ports).select_related("rear_port")
        ]
    if rear_ports:
        onward += [
            pm.front_port for pm in PortMapping.objects.filter(rear_port__in=rear_ports).select_related("front_port")
        ]
    if terminations:
        onward += list(
            CircuitTermination.objects.filter(circuit_id__in=[ct.circuit_id for ct in terminations]).exclude(
                pk__in=[ct.pk for ct in terminations]
            )
        )

    return [obj for obj in onward if obj.cable_id]


def _survey_chain(origin: RearPort, max_hops: int) -> str:
    """Walk the chain structurally and report whether core may safely trace it.

    Returns "ok", "loop" if the walk returns to a set of terminations it has
    already stood on, or "cap" if it is still going after ``max_hops`` cable
    segments.

    Core advances a whole set of terminations at once, one cable segment per
    step, so that set is the walk's state and a repeat of it is what makes
    core spin. Tracking the state rather than individual ports matters for
    unprofiled multi-terminated cables: ``link_peers`` cannot tell their
    strands apart, so both fibres are followed and re-converge on the same
    far ports. That is a diamond, not a cycle, and must not be refused.
    """
    frontier: dict[tuple[str, int], Any] = {_key(origin): origin}
    seen_states = {frozenset(frontier)}

    for _hop in range(max_hops):
        peers = [peer for obj in frontier.values() for peer in obj.link_peers if peer is not None]
        if not peers:
            return "ok"

        onward = {_key(obj): obj for obj in _cross_all(peers)}
        if not onward:
            return "ok"

        state = frozenset(onward)
        if state in seen_states:
            return "loop"
        seen_states.add(state)
        frontier = onward

    return "cap"


def walk_from_rear_port(rear_port: RearPort) -> list[list[Any]] | None:
    """Trace the cable chain leaving a rear port and return its ordered node groups.

    The groups alternate between terminations and the links joining them,
    starting with the origin rear port; see ``CablePath.path_objects``.
    Returns None when the rear port is dark, when the chain cannot be
    proven finite, or when core declines to trace it.
    """
    fresh = RearPort.objects.select_related("device").get(pk=rear_port.pk)
    if not fresh.cable_id:
        return None

    max_hops = get_max_trace_hops()
    verdict = _survey_chain(fresh, max_hops)
    if verdict == "loop":
        logger.warning(
            "Cable trace from rear port %s on device %s returns to ports it has already passed through; "
            "the chain loops back on itself and was not traced. Check the cabling for a patch that "
            "returns to an earlier port.",
            fresh,
            fresh.device,
        )
        return None
    if verdict == "cap":
        logger.warning(
            "Cable trace from rear port %s on device %s stopped after %d cable segments; the traced path "
            "may be incomplete. Raise the max_trace_hops plugin setting if the chain is legitimately longer.",
            fresh,
            fresh.device,
            max_hops,
        )
        return None

    path = CablePath.from_origin([fresh])
    if path is None:
        return None
    return path.path_objects
