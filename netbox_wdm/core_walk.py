"""Spike prototype: delegate one wavelength trunk segment to core CablePath.

Ephemeral entry shim for tracing "channel position N from this trunk
RearPort" with the stock ``CablePath.from_origin`` walk. The returned
CablePath instance is NEVER saved: persisting plugin-originated rows into
core's cablepath table would expose them to core's retrace/delete signal
handlers, which re-run ``from_origin`` on origins core does not know how
to seed and would delete the row.

Seeding mechanism (no vendored loop): ``from_origin`` derives the initial
cable positions for the first profiled-cable hop from the origin
termination's own in-memory ``cable_positions`` whenever its position
stack is empty (dcim/models/cables.py, step 6 profiled-cable fallback).
Overriding that attribute on a freshly fetched instance narrows the walk
to a single position; nothing is written back to the database.

This only selects the intended channel when every cable in the run uses a
channel-space profile (connector position count >= the trunk rear port's
position count), so that PortMapping rear/front positions and cable
connector positions share one position namespace. With strand-space
profiles (e.g. trunk-2c1p) the walk cannot carry a channel position
across a cable hop; see the spike experiments in
tests/test_spike_cablepath.py.
"""

from __future__ import annotations

from dcim.models import RearPort
from dcim.models.cables import CablePath


def trace_segment_from_rear_port(rear_port: RearPort, position: int) -> CablePath | None:
    """Run core CablePath.from_origin seeded at (rear_port, position).

    Returns an UNSAVED CablePath (ephemeral), or None when the rear port
    is not cabled. ``position`` is the channel slot on the rear port
    (PortMapping rear_port_position), which must equal the cable
    connector position under channel-space cable profiles.
    """
    origin = RearPort.objects.get(pk=rear_port.pk)
    if not origin.cable_id:
        return None
    # In-memory seed only -- never saved back.
    origin.cable_positions = [position]
    return CablePath.from_origin([origin])
