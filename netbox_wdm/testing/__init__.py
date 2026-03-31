"""Shared test topology builders for the netbox-wdm plugin.

Used by both the sample data management command and the test suite.
"""

from __future__ import annotations

from .cabling import cable_duplex_through_pp_pair, cable_through_pp_pair
from .dcim import create_device_roles, create_manufacturer, create_site
from .device_types import (
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_dwdm_mux_dx_type,
    create_edfa_type,
    create_fiber_pp_type,
    create_roadm_2d_type,
    create_router_type,
)
from .devices import WdmDeviceBundle, create_duplex_mux, create_patch_panel, create_roadm, create_sf_mux
from .topologies import Topology, duplex_mux_pair, dwdm_mux_to_roadm, mux_roadm_mux, sf_mux_pair

__all__ = [
    "cable_duplex_through_pp_pair",
    "cable_through_pp_pair",
    "create_cwdm_mux_dx_type",
    "create_cwdm_mux_sf_type",
    "create_device_roles",
    "create_duplex_mux",
    "create_dwdm_mux_dx_type",
    "create_edfa_type",
    "create_fiber_pp_type",
    "create_manufacturer",
    "create_patch_panel",
    "create_roadm",
    "create_roadm_2d_type",
    "create_router_type",
    "create_sf_mux",
    "create_site",
    "duplex_mux_pair",
    "dwdm_mux_to_roadm",
    "mux_roadm_mux",
    "sf_mux_pair",
    "Topology",
    "WdmDeviceBundle",
]
