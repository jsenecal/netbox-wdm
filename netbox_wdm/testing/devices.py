"""Device instance builders. Create devices with WDM nodes, line ports, and channels."""

from __future__ import annotations

from dataclasses import dataclass

from dcim.models import Device, DeviceRole, DeviceType, Module, ModuleBay, ModuleType, Site

from netbox_wdm.choices import WdmGridChoices, WdmLineRoleChoices, WdmNodeTypeChoices
from netbox_wdm.models import WdmChannel, WdmLinePort, WdmNode


@dataclass
class WdmDeviceBundle:
    """All objects created for a WDM device."""

    device: Device
    node: WdmNode
    line_ports: dict[str, WdmLinePort]
    channels: list[WdmChannel]


def ensure_populated(node: WdmNode) -> None:
    """Repair a WdmNode whose auto-populate ran before its ports existed.

    In transaction=True test mode, on_commit fires immediately during
    Device.save(), causing auto-populate to run before FrontPorts/RearPorts
    exist. Detect that (channels with no ports assigned) and repopulate.
    """
    if node.channels.filter(mux_front_port__isnull=True, demux_front_port__isnull=True).exists():
        node.channels.all().delete()
        node.line_ports.all().delete()
        node._auto_populate()


def create_duplex_mux(
    site: Site, device_type: DeviceType, role: DeviceRole, name: str, grid: str = WdmGridChoices.CWDM
) -> WdmDeviceBundle:
    """Create a duplex MUX device with WDM node, line ports, and channels."""
    device = Device.objects.create(name=name, site=site, device_type=device_type, role=role)
    node, _ = WdmNode.objects.get_or_create(
        device=device,
        defaults={"node_type": WdmNodeTypeChoices.TERMINAL_MUX, "grid": grid},
    )
    ensure_populated(node)
    lp_tx = WdmLinePort.objects.get(wdm_node=node, role=WdmLineRoleChoices.TX)
    lp_rx = WdmLinePort.objects.get(wdm_node=node, role=WdmLineRoleChoices.RX)
    channels = list(node.channels.order_by("grid_position"))
    return WdmDeviceBundle(device=device, node=node, line_ports={"tx": lp_tx, "rx": lp_rx}, channels=channels)


def create_sf_mux(
    site: Site, device_type: DeviceType, role: DeviceRole, name: str, grid: str = WdmGridChoices.CWDM
) -> WdmDeviceBundle:
    """Create a single-fiber MUX device."""
    device = Device.objects.create(name=name, site=site, device_type=device_type, role=role)
    node, _ = WdmNode.objects.get_or_create(
        device=device,
        defaults={"node_type": WdmNodeTypeChoices.TERMINAL_MUX, "grid": grid},
    )
    ensure_populated(node)
    lp_bidi = WdmLinePort.objects.get(wdm_node=node, role=WdmLineRoleChoices.BIDI)
    channels = list(node.channels.order_by("grid_position"))
    return WdmDeviceBundle(device=device, node=node, line_ports={"bidi": lp_bidi}, channels=channels)


def create_roadm(
    site: Site, device_type: DeviceType, role: DeviceRole, name: str, grid: str = WdmGridChoices.DWDM_100GHZ
) -> WdmDeviceBundle:
    """Create a 2-degree ROADM."""
    device = Device.objects.create(name=name, site=site, device_type=device_type, role=role)
    node, _ = WdmNode.objects.get_or_create(
        device=device,
        defaults={"node_type": WdmNodeTypeChoices.ROADM, "grid": grid},
    )
    ensure_populated(node)
    line_ports = {f"line_{lp.direction}_{lp.role}": lp for lp in node.line_ports.select_related("rear_port")}
    channels = list(node.channels.order_by("grid_position"))
    return WdmDeviceBundle(device=device, node=node, line_ports=line_ports, channels=channels)


def create_patch_panel(site: Site, device_type: DeviceType, role: DeviceRole, name: str) -> Device:
    """Create a fiber patch panel device. Returns the Device (no WDM node)."""
    return Device.objects.create(name=name, site=site, device_type=device_type, role=role)


@dataclass
class ChassisBundle:
    """A modular chassis device with its WDM node and installed cassette modules."""

    device: Device
    node: WdmNode
    modules: dict[str, Module]


def create_modular_chassis(
    site: Site,
    role: DeviceRole,
    name: str,
    mt_cassette: ModuleType,
    bays: tuple[str, ...] = ("MUX1", "MUX2"),
) -> ChassisBundle:
    """Create a bare 1RU chassis device, install one cassette per bay, then create the WdmNode."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=mt_cassette.manufacturer,
        slug="wdm-chassis-1ru",
        defaults={"model": "WDM-CHASSIS-1RU", "u_height": 1},
    )
    device = Device.objects.create(name=name, site=site, device_type=dt, role=role)
    modules = {}
    for bay_name in bays:
        bay = ModuleBay.objects.create(device=device, name=bay_name, position=bay_name)
        modules[bay_name] = Module.objects.create(device=device, module_bay=bay, module_type=mt_cassette)
    node = WdmNode.objects.create(device=device)
    ensure_populated(node)
    return ChassisBundle(device=device, node=node, modules=modules)
