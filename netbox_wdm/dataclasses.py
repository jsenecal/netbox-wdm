"""Shared dataclasses for structured data across the plugin.

Used by models, views, API endpoints, and trace algorithm to avoid
untyped dict[str, Any] patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PortInfo:
    """Reference to a front port with navigation URL."""

    id: int
    name: str
    url: str


@dataclass
class PathElement:
    """A WDM node element in a wavelength path."""

    sequence: int
    node_id: int
    node_name: str
    node_url: str
    channel_id: int
    channel_label: str
    channel_url: str
    wavelength_nm: Decimal
    mux_port: PortInfo | None
    demux_port: PortInfo | None
    mux_connected: bool
    demux_connected: bool


def path_element_from_channel(channel: object, sequence: int) -> PathElement:
    """Build a PathElement from a WdmChannel instance.

    Accepts `object` type to avoid circular import with models.
    The caller must pass a WdmChannel instance.
    """
    ch = channel  # type: ignore[assignment]
    return PathElement(
        sequence=sequence,
        node_id=ch.wdm_node_id,
        node_name=ch.wdm_node.device.name,
        node_url=ch.wdm_node.device.get_absolute_url(),
        channel_id=ch.pk,
        channel_label=ch.label,
        channel_url=ch.get_absolute_url(),
        wavelength_nm=ch.wavelength_nm,
        mux_port=PortInfo(
            id=ch.mux_front_port_id,
            name=ch.mux_front_port.name,
            url=ch.mux_front_port.get_absolute_url(),
        )
        if ch.mux_front_port
        else None,
        demux_port=PortInfo(
            id=ch.demux_front_port_id,
            name=ch.demux_front_port.name,
            url=ch.demux_front_port.get_absolute_url(),
        )
        if ch.demux_front_port
        else None,
        mux_connected=bool(ch.mux_front_port and ch.mux_front_port.cable_id),  # type: ignore[attr-defined]
        demux_connected=bool(ch.demux_front_port and ch.demux_front_port.cable_id),  # type: ignore[attr-defined]
    )


@dataclass
class CableSegmentItem:
    """A single physical element in a cable segment between WDM nodes."""

    type: str  # "rear_port", "cable", "front_port"
    id: int
    name: str
    url: str
    device: str = ""
    label: str = ""
    status: str = ""
    color: str = ""


@dataclass
class CableSegment:
    """The physical cable path between two consecutive path elements."""

    from_sequence: int
    to_sequence: int
    items: list[CableSegmentItem] = field(default_factory=list)


@dataclass
class ChannelTraceData:
    """Complete trace data for a channel's wavelength path."""

    channel_id: int
    wavelength_path_id: int | None
    wavelength_nm: Decimal | None
    grid_position: int
    is_complete: bool
    is_active: bool
    is_valid: bool
    elements: list[PathElement] = field(default_factory=list)
    cable_segments: list[CableSegment] = field(default_factory=list)
