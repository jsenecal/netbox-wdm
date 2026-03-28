"""Device type factories: create DeviceTypes with port templates, PortTemplateMappings, and WDM profiles."""

from dcim.models import DeviceType, FrontPortTemplate, InterfaceTemplate, RearPortTemplate
from dcim.models.device_component_templates import PortTemplateMapping

from netbox_wdm.choices import WdmFiberTypeChoices, WdmGridChoices, WdmNodeTypeChoices
from netbox_wdm.models import WdmChannelPlan, WdmProfile
from netbox_wdm.wdm_constants import CWDM_CHANNELS, DWDM_100GHZ_CHANNELS


def create_cwdm_mux_dx_type(manufacturer, num_channels=8):
    """CWDM duplex MUX: CH{n}-MUX/DEMUX + EXP + 1310 front ports, COM-TX/RX rear ports."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug=f"cwdm-mux-{num_channels}-dx",
        defaults={"model": f"CWDM-MUX-{num_channels}-DX", "u_height": 1},
    )

    # Rear ports: COM-TX and COM-RX with num_channels + 2 positions (channels + EXP + 1310)
    num_positions = num_channels + 2
    com_tx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="COM-TX", defaults={"type": "lc-apc", "positions": num_positions}
    )
    com_rx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="COM-RX", defaults={"type": "lc-apc", "positions": num_positions}
    )

    # Front ports: CH{n}-MUX, CH{n}-DEMUX for each channel
    mux_fps = []
    demux_fps = []
    for i in range(1, num_channels + 1):
        fp_mux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"CH{i}-MUX", defaults={"type": "lc-upc"}
        )
        fp_demux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"CH{i}-DEMUX", defaults={"type": "lc-upc"}
        )
        mux_fps.append(fp_mux)
        demux_fps.append(fp_demux)

    # EXP-MUX, EXP-DEMUX
    exp_mux, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="EXP-MUX", defaults={"type": "lc-upc"})
    exp_demux, _ = FrontPortTemplate.objects.get_or_create(
        device_type=dt, name="EXP-DEMUX", defaults={"type": "lc-upc"}
    )

    # 1310-MUX, 1310-DEMUX
    gray_mux, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="1310-MUX", defaults={"type": "lc-upc"})
    gray_demux, _ = FrontPortTemplate.objects.get_or_create(
        device_type=dt, name="1310-DEMUX", defaults={"type": "lc-upc"}
    )

    # PortTemplateMappings
    all_mux = mux_fps + [exp_mux, gray_mux]
    all_demux = demux_fps + [exp_demux, gray_demux]
    for pos_idx, (fp_mux, fp_demux) in enumerate(zip(all_mux, all_demux, strict=True), start=1):
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_mux,
            rear_port=com_tx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_demux,
            rear_port=com_rx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )

    # WDM Profile + Channel Plans
    profile, _ = WdmProfile.objects.get_or_create(
        device_type=dt,
        defaults={
            "node_type": WdmNodeTypeChoices.TERMINAL_MUX,
            "grid": WdmGridChoices.CWDM,
            "fiber_type": WdmFiberTypeChoices.DUPLEX,
        },
    )
    for i, (fp_mux, fp_demux) in enumerate(zip(mux_fps, demux_fps, strict=True)):
        pos, label, wl = CWDM_CHANNELS[i]
        WdmChannelPlan.objects.get_or_create(
            profile=profile,
            grid_position=pos,
            defaults={
                "wavelength_nm": wl,
                "label": label,
                "mux_front_port_template": fp_mux,
                "demux_front_port_template": fp_demux,
            },
        )

    return dt


def create_cwdm_mux_sf_type(manufacturer, num_channels=8):
    """CWDM single-fiber (BiDi) MUX: CH{n} + EXP + 1310 front ports, single COM rear port."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug=f"cwdm-mux-{num_channels}-sf",
        defaults={"model": f"CWDM-MUX-{num_channels}-SF", "u_height": 1},
    )

    num_positions = num_channels + 2
    com, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="COM", defaults={"type": "lc-apc", "positions": num_positions}
    )

    fps = []
    for i in range(1, num_channels + 1):
        fp, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name=f"CH{i}", defaults={"type": "lc-upc"})
        fps.append(fp)

    exp, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="EXP", defaults={"type": "lc-upc"})
    gray, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="1310", defaults={"type": "lc-upc"})
    fps.extend([exp, gray])

    for pos_idx, fp in enumerate(fps, start=1):
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp,
            rear_port=com,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )

    # WDM Profile + Channel Plans (single-fiber: mux_front_port_template only, no demux)
    profile, _ = WdmProfile.objects.get_or_create(
        device_type=dt,
        defaults={
            "node_type": WdmNodeTypeChoices.TERMINAL_MUX,
            "grid": WdmGridChoices.CWDM,
            "fiber_type": WdmFiberTypeChoices.SINGLE_FIBER,
        },
    )
    # Channel FPs are the first num_channels entries in fps (before EXP and 1310)
    channel_fps = fps[:num_channels]
    for i, fp_ch in enumerate(channel_fps):
        pos, label, wl = CWDM_CHANNELS[i]
        WdmChannelPlan.objects.get_or_create(
            profile=profile,
            grid_position=pos,
            defaults={
                "wavelength_nm": wl,
                "label": label,
                "mux_front_port_template": fp_ch,
                "demux_front_port_template": None,
            },
        )

    return dt


def create_dwdm_mux_dx_type(manufacturer, num_channels=44):
    """DWDM duplex MUX: DWDM label-based front ports + EXP, COM-TX/RX rear ports."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug=f"dwdm-mux-{num_channels}-dx",
        defaults={"model": f"DWDM-MUX-{num_channels}-DX", "u_height": 1},
    )

    num_positions = num_channels + 1  # channels + EXP
    com_tx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="COM-TX", defaults={"type": "lc-apc", "positions": num_positions}
    )
    com_rx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="COM-RX", defaults={"type": "lc-apc", "positions": num_positions}
    )

    mux_fps = []
    demux_fps = []
    for _pos, label, _wl in DWDM_100GHZ_CHANNELS[:num_channels]:
        fp_mux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"{label}-MUX", defaults={"type": "lc-upc"}
        )
        fp_demux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"{label}-DEMUX", defaults={"type": "lc-upc"}
        )
        mux_fps.append(fp_mux)
        demux_fps.append(fp_demux)

    # EXP ports
    exp_mux, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="EXP-MUX", defaults={"type": "lc-upc"})
    exp_demux, _ = FrontPortTemplate.objects.get_or_create(
        device_type=dt, name="EXP-DEMUX", defaults={"type": "lc-upc"}
    )
    mux_fps.append(exp_mux)
    demux_fps.append(exp_demux)

    for pos_idx, (fp_mux, fp_demux) in enumerate(zip(mux_fps, demux_fps, strict=True), start=1):
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_mux,
            rear_port=com_tx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_demux,
            rear_port=com_rx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )

    # WDM Profile + Channel Plans (exclude EXP ports which are the last pair)
    profile, _ = WdmProfile.objects.get_or_create(
        device_type=dt,
        defaults={
            "node_type": WdmNodeTypeChoices.TERMINAL_MUX,
            "grid": WdmGridChoices.DWDM_100GHZ,
            "fiber_type": WdmFiberTypeChoices.DUPLEX,
        },
    )
    channel_mux_fps = mux_fps[:-1]  # exclude EXP
    channel_demux_fps = demux_fps[:-1]
    for i, (fp_mux, fp_demux) in enumerate(zip(channel_mux_fps, channel_demux_fps, strict=True)):
        pos, label, wl = DWDM_100GHZ_CHANNELS[i]
        WdmChannelPlan.objects.get_or_create(
            profile=profile,
            grid_position=pos,
            defaults={
                "wavelength_nm": wl,
                "label": label,
                "mux_front_port_template": fp_mux,
                "demux_front_port_template": fp_demux,
            },
        )

    return dt


def create_edfa_type(manufacturer):
    """EDFA amplifier: LINE-IN front port, LINE-OUT rear port with pass-through mapping."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug="edfa-1ru",
        defaults={"model": "EDFA-1RU", "u_height": 1},
    )

    line_in, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name="LINE-IN", defaults={"type": "lc-apc"})
    line_out, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="LINE-OUT", defaults={"type": "lc-apc", "positions": 1}
    )

    PortTemplateMapping.objects.get_or_create(
        device_type=dt,
        front_port=line_in,
        rear_port=line_out,
        defaults={"front_port_position": 1, "rear_port_position": 1},
    )

    return dt


def create_roadm_2d_type(manufacturer, num_add_drop=20):
    """2-degree ROADM: ADD/DROP front ports, LINE-{dir}-TX/RX rear ports."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug="roadm-2d",
        defaults={"model": "ROADM-2D", "u_height": 2},
    )

    # Rear ports: 4 line ports with 44 positions each
    line_east_tx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="LINE-EAST-TX", defaults={"type": "lc-apc", "positions": 44}
    )
    line_east_rx, _ = RearPortTemplate.objects.get_or_create(
        device_type=dt, name="LINE-EAST-RX", defaults={"type": "lc-apc", "positions": 44}
    )
    RearPortTemplate.objects.get_or_create(
        device_type=dt, name="LINE-WEST-TX", defaults={"type": "lc-apc", "positions": 44}
    )
    RearPortTemplate.objects.get_or_create(
        device_type=dt, name="LINE-WEST-RX", defaults={"type": "lc-apc", "positions": 44}
    )

    # Front ports: ADD-01..ADD-N, DROP-01..DROP-N
    add_fps = []
    drop_fps = []
    for i in range(1, num_add_drop + 1):
        fp_add, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"ADD-{i:02d}", defaults={"type": "lc-upc"}
        )
        fp_drop, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name=f"DROP-{i:02d}", defaults={"type": "lc-upc"}
        )
        add_fps.append(fp_add)
        drop_fps.append(fp_drop)

    # PortTemplateMappings: ADD -> LINE-EAST-TX, DROP -> LINE-EAST-RX
    for pos_idx, (fp_add, fp_drop) in enumerate(zip(add_fps, drop_fps, strict=True), start=1):
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_add,
            rear_port=line_east_tx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp_drop,
            rear_port=line_east_rx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )

    # WDM Profile + Channel Plans (ROADM uses ADD as mux, DROP as demux)
    profile, _ = WdmProfile.objects.get_or_create(
        device_type=dt,
        defaults={
            "node_type": WdmNodeTypeChoices.ROADM,
            "grid": WdmGridChoices.DWDM_100GHZ,
            "fiber_type": WdmFiberTypeChoices.DUPLEX,
        },
    )
    for i, (fp_add, fp_drop) in enumerate(zip(add_fps, drop_fps, strict=True)):
        pos, label, wl = DWDM_100GHZ_CHANNELS[i]
        WdmChannelPlan.objects.get_or_create(
            profile=profile,
            grid_position=pos,
            defaults={
                "wavelength_nm": wl,
                "label": label,
                "mux_front_port_template": fp_add,
                "demux_front_port_template": fp_drop,
            },
        )

    return dt


def create_fiber_pp_type(manufacturer, num_ports=24):
    """Fiber patch panel: 1:1 front-to-rear pass-through ports."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug=f"fiber-pp-{num_ports}",
        defaults={"model": f"Fiber-PP-{num_ports}", "u_height": 1},
    )

    for i in range(1, num_ports + 1):
        fp, _ = FrontPortTemplate.objects.get_or_create(device_type=dt, name=f"FP-{i:02d}", defaults={"type": "lc-upc"})
        rp, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name=f"RP-{i:02d}", defaults={"type": "lc-apc", "positions": 1}
        )
        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=fp,
            rear_port=rp,
            defaults={"front_port_position": 1, "rear_port_position": 1},
        )

    return dt


def create_router_type(manufacturer, num_interfaces=8):
    """Simple router DeviceType with Ethernet interfaces."""
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        slug=f"generic-router-{num_interfaces}p",
        defaults={"model": f"Generic Router {num_interfaces}-Port", "u_height": 1},
    )

    for i in range(num_interfaces):
        InterfaceTemplate.objects.get_or_create(device_type=dt, name=f"eth{i}", defaults={"type": "1000base-t"})

    return dt
