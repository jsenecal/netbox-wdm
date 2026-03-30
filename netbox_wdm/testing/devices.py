"""Device instance builders. Create devices with WDM nodes, line ports, and channels."""

from __future__ import annotations

from dataclasses import dataclass

from dcim.models import Device, DeviceRole, DeviceType, RearPort, Site

from netbox_wdm.choices import WdmGridChoices, WdmLineDirectionChoices, WdmLineRoleChoices, WdmNodeTypeChoices
from netbox_wdm.models import WdmChannel, WdmLinePort, WdmNode


@dataclass
class WdmDeviceBundle:
    """All objects created for a WDM device."""

    device: Device
    node: WdmNode
    line_ports: dict[str, WdmLinePort]
    channels: list[WdmChannel]


def create_duplex_mux(
    site: Site, device_type: DeviceType, role: DeviceRole, name: str, grid: str = WdmGridChoices.CWDM
) -> WdmDeviceBundle:
    """Create a duplex MUX device with WDM node, line ports, and channels."""
    device = Device.objects.create(name=name, site=site, device_type=device_type, role=role)
    node, _ = WdmNode.objects.get_or_create(
        device=device,
        defaults={"node_type": WdmNodeTypeChoices.TERMINAL_MUX, "grid": grid},
    )
    com_tx = RearPort.objects.get(device=device, name="COM-TX")
    com_rx = RearPort.objects.get(device=device, name="COM-RX")
    lp_tx, _ = WdmLinePort.objects.get_or_create(
        wdm_node=node,
        rear_port=com_tx,
        defaults={"direction": WdmLineDirectionChoices.COMMON, "role": WdmLineRoleChoices.TX},
    )
    lp_rx, _ = WdmLinePort.objects.get_or_create(
        wdm_node=node,
        rear_port=com_rx,
        defaults={"direction": WdmLineDirectionChoices.COMMON, "role": WdmLineRoleChoices.RX},
    )
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
    com = RearPort.objects.get(device=device, name="COM")
    lp_bidi, _ = WdmLinePort.objects.get_or_create(
        wdm_node=node,
        rear_port=com,
        defaults={"direction": WdmLineDirectionChoices.COMMON, "role": WdmLineRoleChoices.BIDI},
    )
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
    line_ports = {}
    for rp_name, direction, lp_role in [
        ("LINE-EAST-TX", WdmLineDirectionChoices.EAST, WdmLineRoleChoices.TX),
        ("LINE-EAST-RX", WdmLineDirectionChoices.EAST, WdmLineRoleChoices.RX),
        ("LINE-WEST-TX", WdmLineDirectionChoices.WEST, WdmLineRoleChoices.TX),
        ("LINE-WEST-RX", WdmLineDirectionChoices.WEST, WdmLineRoleChoices.RX),
    ]:
        rp = RearPort.objects.get(device=device, name=rp_name)
        lp, _ = WdmLinePort.objects.get_or_create(
            wdm_node=node,
            rear_port=rp,
            defaults={"direction": direction, "role": lp_role},
        )
        line_ports[rp_name.lower().replace("-", "_")] = lp
    channels = list(node.channels.order_by("grid_position"))
    return WdmDeviceBundle(device=device, node=node, line_ports=line_ports, channels=channels)


def create_patch_panel(site: Site, device_type: DeviceType, role: DeviceRole, name: str) -> Device:
    """Create a fiber patch panel device. Returns the Device (no WDM node)."""
    return Device.objects.create(name=name, site=site, device_type=device_type, role=role)
