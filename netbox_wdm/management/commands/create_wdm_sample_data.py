"""Create comprehensive sample data for the netbox-wdm plugin.

Demonstrates realistic WDM hardware topologies with full end-to-end cabling:
  - Duplex and single-fiber CWDM MUX devices
  - DWDM 100GHz 44-channel MUX
  - EDFA amplifier with CablePath pass-through
  - ROADM 2-degree with add/drop ports
  - Fiber patch panels (pure DCIM, no WDM profile)
  - End-to-end cabling from router through mux, patch panel, trunk, and back
  - Wavelength services in various lifecycle states

Usage:
    cd /opt/netbox/netbox
    python manage.py create_wdm_sample_data
    python manage.py create_wdm_sample_data --flush   # remove sample data first
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_wdm.wdm_constants import CWDM_CHANNELS, DWDM_100GHZ_CHANNELS

# Tag used to identify sample data for cleanup
SAMPLE_TAG = "wdm-sample-data"


class Command(BaseCommand):
    help = "Create comprehensive WDM sample data demonstrating all plugin features."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Remove all existing sample data (tagged with 'wdm-sample-data') before creating new data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        tag = self._get_or_create_tag()

        # -- DCIM foundation --
        manufacturer = self._create_manufacturer(tag)
        site_east, site_west, site_hub = self._create_sites(tag)
        role_mux, role_roadm, role_amp, role_pp, role_router = self._create_device_roles(tag)

        # -- DeviceTypes with port templates and mappings --
        dt_cwdm_dx = self._create_cwdm_mux_8_dx(manufacturer, tag)
        dt_cwdm_sf = self._create_cwdm_mux_8_sf(manufacturer, tag)
        dt_dwdm_44 = self._create_dwdm_mux_44_dx(manufacturer, tag)
        dt_edfa = self._create_edfa_1ru(manufacturer, tag)
        dt_roadm = self._create_roadm_2d(manufacturer, tag)
        dt_pp = self._create_fiber_pp_24(manufacturer, tag)
        dt_router = self._create_router_device_type(manufacturer, tag)

        # -- WDM Profiles on DeviceTypes (not on Fiber-PP-24 or Router) --
        self._create_profiles(tag, dt_cwdm_dx, dt_cwdm_sf, dt_dwdm_44, dt_edfa, dt_roadm)

        # -- Channel templates --
        self._create_channel_templates(tag, dt_cwdm_dx, dt_cwdm_sf, dt_dwdm_44, dt_roadm)

        # -- Devices --
        dev_east_cwdm = self._create_device("EAST-CWDM-MUX-01", site_east, dt_cwdm_dx, role_mux, tag)
        dev_east_pp = self._create_device("EAST-PP-01", site_east, dt_pp, role_pp, tag)
        dev_east_sf = self._create_device("EAST-CWDM-SF-01", site_east, dt_cwdm_sf, role_mux, tag)
        dev_east_router = self._create_device("EAST-ROUTER-01", site_east, dt_router, role_router, tag)

        dev_west_cwdm = self._create_device("WEST-CWDM-MUX-01", site_west, dt_cwdm_dx, role_mux, tag)
        dev_west_pp = self._create_device("WEST-PP-01", site_west, dt_pp, role_pp, tag)
        dev_west_router = self._create_device("WEST-ROUTER-01", site_west, dt_router, role_router, tag)

        dev_hub_dwdm = self._create_device("HUB-DWDM-MUX-01", site_hub, dt_dwdm_44, role_mux, tag)
        dev_hub_roadm = self._create_device("HUB-ROADM-01", site_hub, dt_roadm, role_roadm, tag)
        self._create_device("HUB-EDFA-01", site_hub, dt_edfa, role_amp, tag)
        self._create_device("HUB-PP-01", site_hub, dt_pp, role_pp, tag)
        self._create_device("HUB-PP-02", site_hub, dt_pp, role_pp, tag)

        # -- Line ports --
        self._create_line_ports(
            tag,
            dev_east_cwdm,
            dev_west_cwdm,
            dev_east_sf,
            dev_hub_dwdm,
            dev_hub_roadm,
        )

        # -- Cabling --
        self._create_cables(
            tag,
            dev_east_cwdm,
            dev_east_pp,
            dev_east_sf,
            dev_east_router,
            dev_west_cwdm,
            dev_west_pp,
            dev_west_router,
        )

        # -- Channel configuration --
        self._configure_channels(dev_east_cwdm, dev_west_cwdm)

        # -- Wavelength services --
        self._create_services(tag, dev_east_cwdm, dev_west_cwdm)

        self.stdout.write(self.style.SUCCESS("\nSample data created successfully."))
        self._print_summary()

    # ================================================================
    # Flush
    # ================================================================

    def _flush(self):
        from extras.models import Tag

        from netbox_wdm.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceNode,
            WdmChannelTemplate,
            WdmDeviceTypeProfile,
            WdmLinePort,
            WdmNode,
        )

        self.stdout.write("Flushing existing sample data...")

        try:
            tag = Tag.objects.get(slug=SAMPLE_TAG)
        except Tag.DoesNotExist:
            self.stdout.write("  No sample data tag found, nothing to flush.")
            return

        from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Site

        # Delete cables first (they hold termination references to ports)
        Cable.objects.filter(tags=tag).delete()

        # Then WDM objects in dependency order
        WavelengthServiceNode.objects.filter(service__tags=tag).delete()
        WavelengthServiceChannelAssignment.objects.filter(service__tags=tag).delete()
        WavelengthService.objects.filter(tags=tag).delete()
        WavelengthChannel.objects.filter(wdm_node__tags=tag).delete()
        WdmLinePort.objects.filter(wdm_node__tags=tag).delete()
        WdmNode.objects.filter(tags=tag).delete()
        WdmChannelTemplate.objects.filter(profile__tags=tag).delete()
        WdmDeviceTypeProfile.objects.filter(tags=tag).delete()

        # Then DCIM objects
        Device.objects.filter(tags=tag).delete()
        DeviceType.objects.filter(tags=tag).delete()
        DeviceRole.objects.filter(tags=tag).delete()
        Manufacturer.objects.filter(tags=tag).delete()
        Site.objects.filter(tags=tag).delete()

        self.stdout.write(self.style.SUCCESS("  Flushed."))

    # ================================================================
    # Tag helper
    # ================================================================

    def _get_or_create_tag(self):
        from extras.models import Tag

        tag, created = Tag.objects.get_or_create(
            slug=SAMPLE_TAG,
            defaults={"name": "WDM Sample Data", "color": "2196f3"},
        )
        if created:
            self.stdout.write(f"  Created tag: {tag.name}")
        return tag

    def _tag(self, obj, tag):
        obj.tags.add(tag)
        return obj

    # ================================================================
    # DCIM Foundation
    # ================================================================

    def _create_manufacturer(self, tag):
        from dcim.models import Manufacturer

        mfr, _ = Manufacturer.objects.get_or_create(
            slug="acme-photonics",
            defaults={"name": "Acme Photonics"},
        )
        self._tag(mfr, tag)
        self.stdout.write(f"  Manufacturer: {mfr.name}")
        return mfr

    def _create_sites(self, tag):
        from dcim.models import Site

        sites = []
        for name, slug in [
            ("East Coast POP", "east-coast-pop"),
            ("West Coast POP", "west-coast-pop"),
            ("Central Hub", "central-hub"),
        ]:
            site, _ = Site.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "status": "active"},
            )
            self._tag(site, tag)
            sites.append(site)
            self.stdout.write(f"  Site: {name}")
        return sites

    def _create_device_roles(self, tag):
        from dcim.models import DeviceRole

        roles = []
        for name, slug, color in [
            ("WDM Terminal Mux", "wdm-terminal-mux", "4caf50"),
            ("WDM ROADM", "wdm-roadm", "ff9800"),
            ("WDM Amplifier", "wdm-amplifier", "9c27b0"),
            ("Fiber Patch Panel", "fiber-patch-panel", "607d8b"),
            ("Router", "router", "2196f3"),
        ]:
            role, _ = DeviceRole.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "color": color},
            )
            self._tag(role, tag)
            roles.append(role)
            self.stdout.write(f"  Role: {name}")
        return roles

    # ================================================================
    # DeviceType creation with port templates and PortTemplateMappings
    # ================================================================

    def _create_cwdm_mux_8_dx(self, manufacturer, tag):
        """CWDM-MUX-8-DX: 8-channel duplex CWDM mux."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="cwdm-mux-8-dx",
            defaults={"model": "CWDM-MUX-8-DX", "u_height": 1},
        )
        self._tag(dt, tag)

        # Rear ports: COM-TX and COM-RX with 10 positions (8 ch + EXP + 1310)
        num_positions = 10
        com_tx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="COM-TX", defaults={"type": "lc-apc", "positions": num_positions}
        )
        com_rx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="COM-RX", defaults={"type": "lc-apc", "positions": num_positions}
        )

        # Front ports: CH{n}-MUX, CH{n}-DEMUX for 8 channels
        mux_fps = []
        demux_fps = []
        for i in range(1, 9):
            fp_mux, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"CH{i}-MUX", defaults={"type": "lc-upc"}
            )
            fp_demux, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"CH{i}-DEMUX", defaults={"type": "lc-upc"}
            )
            mux_fps.append(fp_mux)
            demux_fps.append(fp_demux)

        # EXP-MUX, EXP-DEMUX
        exp_mux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name="EXP-MUX", defaults={"type": "lc-upc"}
        )
        exp_demux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name="EXP-DEMUX", defaults={"type": "lc-upc"}
        )

        # 1310-MUX, 1310-DEMUX
        gray_mux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name="1310-MUX", defaults={"type": "lc-upc"}
        )
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

        self.stdout.write("  DeviceType: CWDM-MUX-8-DX (20 front, 2 rear, duplex)")
        return dt

    def _create_cwdm_mux_8_sf(self, manufacturer, tag):
        """CWDM-MUX-8-SF: 8-channel single-fiber (BiDi) CWDM mux."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="cwdm-mux-8-sf",
            defaults={"model": "CWDM-MUX-8-SF", "u_height": 1},
        )
        self._tag(dt, tag)

        num_positions = 10
        com, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="COM", defaults={"type": "lc-apc", "positions": num_positions}
        )

        fps = []
        for i in range(1, 9):
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

        self.stdout.write("  DeviceType: CWDM-MUX-8-SF (10 front, 1 rear, single fiber)")
        return dt

    def _create_dwdm_mux_44_dx(self, manufacturer, tag):
        """DWDM-MUX-44-DX: 44-channel duplex DWDM 100GHz mux."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="dwdm-mux-44-dx",
            defaults={"model": "DWDM-MUX-44-DX", "u_height": 1},
        )
        self._tag(dt, tag)

        num_positions = 45  # 44 channels + EXP
        com_tx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="COM-TX", defaults={"type": "lc-apc", "positions": num_positions}
        )
        com_rx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="COM-RX", defaults={"type": "lc-apc", "positions": num_positions}
        )

        mux_fps = []
        demux_fps = []
        for _pos, label, _wl in DWDM_100GHZ_CHANNELS:
            fp_mux, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"{label}-MUX", defaults={"type": "lc-upc"}
            )
            fp_demux, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"{label}-DEMUX", defaults={"type": "lc-upc"}
            )
            mux_fps.append(fp_mux)
            demux_fps.append(fp_demux)

        # EXP ports
        exp_mux, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name="EXP-MUX", defaults={"type": "lc-upc"}
        )
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

        self.stdout.write("  DeviceType: DWDM-MUX-44-DX (90 front, 2 rear, duplex)")
        return dt

    def _create_edfa_1ru(self, manufacturer, tag):
        """EDFA-1RU: amplifier with FrontPort/RearPort for CablePath pass-through."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="edfa-1ru",
            defaults={"model": "EDFA-1RU", "u_height": 1},
        )
        self._tag(dt, tag)

        line_in, _ = FrontPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-IN", defaults={"type": "lc-apc"}
        )
        line_out, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-OUT", defaults={"type": "lc-apc", "positions": 1}
        )

        PortTemplateMapping.objects.get_or_create(
            device_type=dt,
            front_port=line_in,
            rear_port=line_out,
            defaults={"front_port_position": 1, "rear_port_position": 1},
        )

        self.stdout.write("  DeviceType: EDFA-1RU (1 front, 1 rear, amplifier)")
        return dt

    def _create_roadm_2d(self, manufacturer, tag):
        """ROADM-2D: 2-degree ROADM with add/drop and line ports."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="roadm-2d",
            defaults={"model": "ROADM-2D", "u_height": 2},
        )
        self._tag(dt, tag)

        # Rear ports: 4 line ports with 44 positions each
        line_east_tx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-EAST-TX", defaults={"type": "lc-apc", "positions": 44}
        )
        line_east_rx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-EAST-RX", defaults={"type": "lc-apc", "positions": 44}
        )
        line_west_tx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-WEST-TX", defaults={"type": "lc-apc", "positions": 44}
        )
        line_west_rx, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt, name="LINE-WEST-RX", defaults={"type": "lc-apc", "positions": 44}
        )

        # Front ports: ADD-01..ADD-20, DROP-01..DROP-20
        add_fps = []
        drop_fps = []
        for i in range(1, 21):
            fp_add, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"ADD-{i:02d}", defaults={"type": "lc-upc"}
            )
            fp_drop, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"DROP-{i:02d}", defaults={"type": "lc-upc"}
            )
            add_fps.append(fp_add)
            drop_fps.append(fp_drop)

        # PortTemplateMappings: ADD -> LINE-EAST-TX, DROP -> LINE-EAST-RX
        # (simplified: only mapping to east direction for the first 20 channels)
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

        self.stdout.write("  DeviceType: ROADM-2D (40 front, 4 rear, roadm)")
        return dt

    def _create_fiber_pp_24(self, manufacturer, tag):
        """Fiber-PP-24: 24-port fiber patch panel (no WDM profile)."""
        from dcim.models import DeviceType, FrontPortTemplate, PortTemplateMapping, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="fiber-pp-24",
            defaults={"model": "Fiber-PP-24", "u_height": 1},
        )
        self._tag(dt, tag)

        for i in range(1, 25):
            fp, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt, name=f"FP-{i:02d}", defaults={"type": "lc-upc"}
            )
            rp, _ = RearPortTemplate.objects.get_or_create(
                device_type=dt, name=f"RP-{i:02d}", defaults={"type": "lc-apc", "positions": 1}
            )
            PortTemplateMapping.objects.get_or_create(
                device_type=dt,
                front_port=fp,
                rear_port=rp,
                defaults={"front_port_position": 1, "rear_port_position": 1},
            )

        self.stdout.write("  DeviceType: Fiber-PP-24 (24 front, 24 rear, 1:1 pass-through)")
        return dt

    def _create_router_device_type(self, manufacturer, tag):
        """Simple router DeviceType with 8 Ethernet interfaces."""
        from dcim.models import DeviceType, InterfaceTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="generic-router-8p",
            defaults={"model": "Generic Router 8-Port", "u_height": 1},
        )
        self._tag(dt, tag)

        for i in range(8):
            InterfaceTemplate.objects.get_or_create(device_type=dt, name=f"eth{i}", defaults={"type": "1000base-t"})

        self.stdout.write("  DeviceType: Generic Router 8-Port (8 interfaces)")
        return dt

    # ================================================================
    # WDM Profiles
    # ================================================================

    def _create_profiles(self, tag, dt_cwdm_dx, dt_cwdm_sf, dt_dwdm_44, dt_edfa, dt_roadm):
        from netbox_wdm.models import WdmDeviceTypeProfile

        profiles = [
            (dt_cwdm_dx, "terminal_mux", "cwdm", "duplex"),
            (dt_cwdm_sf, "terminal_mux", "cwdm", "single_fiber"),
            (dt_dwdm_44, "terminal_mux", "dwdm_100ghz", "duplex"),
            (dt_edfa, "amplifier", "dwdm_100ghz", "duplex"),
            (dt_roadm, "roadm", "dwdm_100ghz", "duplex"),
        ]
        for dt, node_type, grid, fiber_type in profiles:
            p, _ = WdmDeviceTypeProfile.objects.get_or_create(
                device_type=dt,
                defaults={"node_type": node_type, "grid": grid, "fiber_type": fiber_type},
            )
            self._tag(p, tag)
            self.stdout.write(f"  Profile: {dt.model} -> {node_type}/{grid}/{fiber_type}")

    # ================================================================
    # Channel Templates
    # ================================================================

    def _create_channel_templates(self, tag, dt_cwdm_dx, dt_cwdm_sf, dt_dwdm_44, dt_roadm):

        # CWDM-MUX-8-DX: first 8 CWDM channels, duplex
        self._create_cwdm_dx_templates(dt_cwdm_dx)

        # CWDM-MUX-8-SF: first 8 CWDM channels, single fiber
        self._create_cwdm_sf_templates(dt_cwdm_sf)

        # DWDM-MUX-44-DX: all 44 DWDM 100GHz channels
        self._create_dwdm_44_templates(dt_dwdm_44)

        # ROADM-2D: first 20 DWDM 100GHz channels
        self._create_roadm_templates(dt_roadm)

    def _create_cwdm_dx_templates(self, dt):
        from dcim.models import FrontPortTemplate

        from netbox_wdm.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.get(device_type=dt)
        fp_templates = {fp.name: fp for fp in FrontPortTemplate.objects.filter(device_type=dt)}

        created = 0
        for pos, label, wavelength in CWDM_CHANNELS[:8]:
            mux_fpt = fp_templates.get(f"CH{pos}-MUX")
            demux_fpt = fp_templates.get(f"CH{pos}-DEMUX")
            _, was_created = WdmChannelTemplate.objects.get_or_create(
                profile=profile,
                grid_position=pos,
                defaults={
                    "wavelength_nm": wavelength,
                    "label": label,
                    "mux_front_port_template": mux_fpt,
                    "demux_front_port_template": demux_fpt,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(f"  Channel templates: CWDM-MUX-8-DX - {created} channels (duplex)")

    def _create_cwdm_sf_templates(self, dt):
        from dcim.models import FrontPortTemplate

        from netbox_wdm.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.get(device_type=dt)
        fp_templates = {fp.name: fp for fp in FrontPortTemplate.objects.filter(device_type=dt)}

        created = 0
        for pos, label, wavelength in CWDM_CHANNELS[:8]:
            mux_fpt = fp_templates.get(f"CH{pos}")
            _, was_created = WdmChannelTemplate.objects.get_or_create(
                profile=profile,
                grid_position=pos,
                defaults={
                    "wavelength_nm": wavelength,
                    "label": label,
                    "mux_front_port_template": mux_fpt,
                    "demux_front_port_template": None,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(f"  Channel templates: CWDM-MUX-8-SF - {created} channels (single fiber)")

    def _create_dwdm_44_templates(self, dt):
        from dcim.models import FrontPortTemplate

        from netbox_wdm.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.get(device_type=dt)
        fp_templates = {fp.name: fp for fp in FrontPortTemplate.objects.filter(device_type=dt)}

        created = 0
        for pos, label, wavelength in DWDM_100GHZ_CHANNELS:
            mux_fpt = fp_templates.get(f"{label}-MUX")
            demux_fpt = fp_templates.get(f"{label}-DEMUX")
            _, was_created = WdmChannelTemplate.objects.get_or_create(
                profile=profile,
                grid_position=pos,
                defaults={
                    "wavelength_nm": wavelength,
                    "label": label,
                    "mux_front_port_template": mux_fpt,
                    "demux_front_port_template": demux_fpt,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(f"  Channel templates: DWDM-MUX-44-DX - {created} channels (duplex)")

    def _create_roadm_templates(self, dt):
        from dcim.models import FrontPortTemplate

        from netbox_wdm.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.get(device_type=dt)
        fp_templates = {fp.name: fp for fp in FrontPortTemplate.objects.filter(device_type=dt)}

        created = 0
        for pos, label, wavelength in DWDM_100GHZ_CHANNELS[:20]:
            mux_fpt = fp_templates.get(f"ADD-{pos:02d}")
            demux_fpt = fp_templates.get(f"DROP-{pos:02d}")
            _, was_created = WdmChannelTemplate.objects.get_or_create(
                profile=profile,
                grid_position=pos,
                defaults={
                    "wavelength_nm": wavelength,
                    "label": label,
                    "mux_front_port_template": mux_fpt,
                    "demux_front_port_template": demux_fpt,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(f"  Channel templates: ROADM-2D - {created} channels")

    # ================================================================
    # Devices
    # ================================================================

    def _create_device(self, name, site, device_type, role, tag):
        from dcim.models import Device

        from netbox_wdm.models import WdmDeviceTypeProfile, WdmNode

        dev, created = Device.objects.get_or_create(
            name=name,
            site=site,
            defaults={"device_type": device_type, "role": role, "status": "active"},
        )
        self._tag(dev, tag)

        # Explicitly create WdmNode (signal uses on_commit which won't fire inside atomic block)
        if not hasattr(dev, "wdm_node"):
            try:
                profile = WdmDeviceTypeProfile.objects.get(device_type=device_type)
                node = WdmNode.objects.create(
                    device=dev,
                    node_type=profile.node_type,
                    grid=profile.grid,
                )
                self._tag(node, tag)
                dev.refresh_from_db()
            except WdmDeviceTypeProfile.DoesNotExist:
                pass
        else:
            self._tag(dev.wdm_node, tag)

        action = "Created" if created else "Exists"
        channel_count = dev.wdm_node.channels.count() if hasattr(dev, "wdm_node") else 0
        self.stdout.write(f"  {action} device: {name} ({channel_count} channels)")
        return dev

    # ================================================================
    # Line Ports
    # ================================================================

    def _create_line_ports(self, tag, dev_east_cwdm, dev_west_cwdm, dev_east_sf, dev_hub_dwdm, dev_hub_roadm):
        from dcim.models import RearPort

        from netbox_wdm.models import WdmLinePort

        # Duplex MUX line ports: COM-TX (tx) and COM-RX (rx)
        for dev in [dev_east_cwdm, dev_west_cwdm, dev_hub_dwdm]:
            if not hasattr(dev, "wdm_node"):
                continue
            for rp_name, role in [("COM-TX", "tx"), ("COM-RX", "rx")]:
                rp = RearPort.objects.filter(device=dev, name=rp_name).first()
                if rp:
                    tp, created = WdmLinePort.objects.get_or_create(
                        wdm_node=dev.wdm_node,
                        rear_port=rp,
                        defaults={"direction": "common", "role": role},
                    )
                    if created:
                        self._tag(tp, tag)
                        self.stdout.write(f"  Line port: {dev.name} -> {rp_name} (common/{role})")

        # Single fiber MUX: COM (bidi)
        if hasattr(dev_east_sf, "wdm_node"):
            rp = RearPort.objects.filter(device=dev_east_sf, name="COM").first()
            if rp:
                tp, created = WdmLinePort.objects.get_or_create(
                    wdm_node=dev_east_sf.wdm_node,
                    rear_port=rp,
                    defaults={"direction": "common", "role": "bidi"},
                )
                if created:
                    self._tag(tp, tag)
                    self.stdout.write(f"  Line port: {dev_east_sf.name} -> COM (common/bidi)")

        # ROADM: 4 line ports
        if hasattr(dev_hub_roadm, "wdm_node"):
            roadm_lines = [
                ("LINE-EAST-TX", "tx", "east"),
                ("LINE-EAST-RX", "rx", "east"),
                ("LINE-WEST-TX", "tx", "west"),
                ("LINE-WEST-RX", "rx", "west"),
            ]
            for rp_name, role, direction in roadm_lines:
                rp = RearPort.objects.filter(device=dev_hub_roadm, name=rp_name).first()
                if rp:
                    tp, created = WdmLinePort.objects.get_or_create(
                        wdm_node=dev_hub_roadm.wdm_node,
                        rear_port=rp,
                        defaults={"direction": direction, "role": role},
                    )
                    if created:
                        self._tag(tp, tag)
                        self.stdout.write(f"  Line port: {dev_hub_roadm.name} -> {rp_name} ({direction}/{role})")

    # ================================================================
    # Cabling
    # ================================================================

    def _create_cables(
        self,
        tag,
        dev_east_cwdm,
        dev_east_pp,
        dev_east_sf,
        dev_east_router,
        dev_west_cwdm,
        dev_west_pp,
        dev_west_router,
    ):
        from dcim.models import Cable, FrontPort, Interface, RearPort

        def get_interface(device, name):
            return Interface.objects.get(device=device, name=name)

        def get_front_port(device, name):
            return FrontPort.objects.get(device=device, name=name)

        def get_rear_port(device, name):
            return RearPort.objects.get(device=device, name=name)

        def create_cable(a_terms, b_terms, label, cable_type="smf-os2"):
            """Create a cable. a_terms and b_terms can be single objects or lists."""
            if not isinstance(a_terms, list):
                a_terms = [a_terms]
            if not isinstance(b_terms, list):
                b_terms = [b_terms]
            cable = Cable(
                type=cable_type,
                status="connected",
                label=label,
                a_terminations=a_terms,
                b_terminations=b_terms,
            )
            cable.save()
            self._tag(cable, tag)
            self.stdout.write(f"  Cable: {label}")
            return cable

        # === East side client cables ===
        # Cable CH1-CH3 and CH6 to router interfaces (CH4-5, CH7-8 left disconnected)
        for i, ch_num in enumerate([1, 2, 3, 6]):
            create_cable(
                get_interface(dev_east_router, f"eth{i}"),
                [
                    get_front_port(dev_east_cwdm, f"CH{ch_num}-MUX"),
                    get_front_port(dev_east_cwdm, f"CH{ch_num}-DEMUX"),
                ],
                f"East Router eth{i} to CWDM CH{ch_num}",
            )

        # CWDM MUX COM-TX + COM-RX -> East PP RP-01 + RP-02 (duplex line pair)
        create_cable(
            [get_rear_port(dev_east_cwdm, "COM-TX"), get_rear_port(dev_east_cwdm, "COM-RX")],
            [get_rear_port(dev_east_pp, "RP-01"), get_rear_port(dev_east_pp, "RP-02")],
            "East CWDM COM to PP",
        )

        # === Line cable (East PP to West PP) - duplex ===
        create_cable(
            [get_front_port(dev_east_pp, "FP-01"), get_front_port(dev_east_pp, "FP-02")],
            [get_front_port(dev_west_pp, "FP-01"), get_front_port(dev_west_pp, "FP-02")],
            "East-West Line Fiber",
        )

        # === West side client cables ===
        # Mirror East: cable CH1-CH3 and CH6
        create_cable(
            [get_rear_port(dev_west_pp, "RP-01"), get_rear_port(dev_west_pp, "RP-02")],
            [get_rear_port(dev_west_cwdm, "COM-TX"), get_rear_port(dev_west_cwdm, "COM-RX")],
            "West PP to CWDM COM",
        )

        for i, ch_num in enumerate([1, 2, 3, 6]):
            create_cable(
                [
                    get_front_port(dev_west_cwdm, f"CH{ch_num}-MUX"),
                    get_front_port(dev_west_cwdm, f"CH{ch_num}-DEMUX"),
                ],
                get_interface(dev_west_router, f"eth{i}"),
                f"West CWDM CH{ch_num} to Router eth{i}",
            )

        # === EXP daisy-chain demo ===
        # EAST-CWDM-MUX-01 EXP-MUX + EXP-DEMUX -> EAST-CWDM-SF-01 COM (duplex to single-fiber)
        create_cable(
            [get_front_port(dev_east_cwdm, "EXP-MUX"), get_front_port(dev_east_cwdm, "EXP-DEMUX")],
            get_rear_port(dev_east_sf, "COM"),
            "East CWDM DX EXP to SF COM (upgrade chain)",
        )

    # ================================================================
    # Channel Configuration
    # ================================================================

    def _configure_channels(self, dev_east_cwdm, dev_west_cwdm):
        """Set channel statuses to demonstrate all combined cable+status states.

        Combined states across 8 channels per MUX:
          CH1: Active   + Connected  (fully operational)
          CH2: Active   + Connected  (fully operational)
          CH3: Reserved + Connected  (wired, held for future use)
          CH4: Active   + Disconnected (problem - service active but no cable!)
          CH5: Reserved + Disconnected (planned, not yet cabled)
          CH6: Available + Connected  (cabled but no service)
          CH7: Available + Disconnected (empty slot)
          CH8: Available + Disconnected (empty slot)

        Cables: CH1,CH2,CH3,CH6 are cabled to router. CH4,CH5,CH7,CH8 are not.
        """
        from netbox_wdm.models import WavelengthChannel

        for dev in [dev_east_cwdm, dev_west_cwdm]:
            if not hasattr(dev, "wdm_node"):
                continue

            channels = list(dev.wdm_node.channels.order_by("grid_position"))
            if len(channels) < 8:
                continue

            channels[0].status = "active"  # CH1: active + connected
            channels[1].status = "active"  # CH2: active + connected
            channels[2].status = "reserved"  # CH3: reserved + connected
            channels[3].status = "active"  # CH4: active + disconnected (problem!)
            channels[4].status = "reserved"  # CH5: reserved + disconnected
            # CH6: available + connected (default status, has cable)
            # CH7: available + disconnected (default)
            # CH8: available + disconnected (default)

            WavelengthChannel.objects.bulk_update(channels[:5], ["status"])
            self.stdout.write(
                f"  Channel status on {dev.name}: "
                f"2 active+connected, 1 reserved+connected, "
                f"1 active+disconnected, 1 reserved+disconnected, "
                f"1 available+connected, 2 available+disconnected"
            )

    # ================================================================
    # Wavelength Services
    # ================================================================

    def _create_services(self, tag, dev_east_cwdm, dev_west_cwdm):
        from netbox_wdm.models import WavelengthService

        east_channels = (
            list(dev_east_cwdm.wdm_node.channels.order_by("grid_position"))
            if hasattr(dev_east_cwdm, "wdm_node")
            else []
        )
        west_channels = (
            list(dev_west_cwdm.wdm_node.channels.order_by("grid_position"))
            if hasattr(dev_west_cwdm, "wdm_node")
            else []
        )

        if not east_channels or not west_channels:
            self.stdout.write(self.style.WARNING("  Skipping services: missing channels"))
            return

        # Service 1: ACTIVE East-West on CH1 (1270nm) - active+connected on both ends
        svc1, created = WavelengthService.objects.get_or_create(
            name="CWDM-1270-EastWest",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[0].wavelength_nm,
                "description": "Active CWDM service, fully cabled East to West.",
            },
        )
        if created:
            self._tag(svc1, tag)
            self._assign_channels(svc1, [east_channels[0], west_channels[0]])
            self.stdout.write(f"  Service: {svc1.name} (ACTIVE, 2-hop, {svc1.wavelength_nm}nm)")

        # Service 2: ACTIVE East-West on CH2 (1290nm) - active+connected
        svc2, created = WavelengthService.objects.get_or_create(
            name="CWDM-1290-EastWest",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[1].wavelength_nm,
                "description": "Active CWDM service, fully cabled East to West.",
            },
        )
        if created:
            self._tag(svc2, tag)
            self._assign_channels(svc2, [east_channels[1], west_channels[1]])
            self.stdout.write(f"  Service: {svc2.name} (ACTIVE, 2-hop, {svc2.wavelength_nm}nm)")

        # Service 3: STAGED East-West on CH3 (1310nm) - reserved+connected
        svc3, created = WavelengthService.objects.get_or_create(
            name="CWDM-1310-Staged",
            defaults={
                "status": "staged",
                "wavelength_nm": east_channels[2].wavelength_nm,
                "description": "Staged service, cabled and reserved, awaiting activation.",
            },
        )
        if created:
            self._tag(svc3, tag)
            self._assign_channels(svc3, [east_channels[2], west_channels[2]])
            self.stdout.write(f"  Service: {svc3.name} (STAGED, 2-hop, {svc3.wavelength_nm}nm)")

        # Service 4: ACTIVE East-only on CH4 (1330nm) - active+DISCONNECTED (problem state!)
        svc4, created = WavelengthService.objects.get_or_create(
            name="CWDM-1330-Fault",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[3].wavelength_nm,
                "description": "Active service on disconnected channel - cable fault or missing patch.",
            },
        )
        if created:
            self._tag(svc4, tag)
            self._assign_channels(svc4, [east_channels[3]])
            self.stdout.write(f"  Service: {svc4.name} (ACTIVE but DISCONNECTED, 1-hop, {svc4.wavelength_nm}nm)")

        # Service 5: PLANNED East-only on CH5 (1350nm) - reserved+disconnected
        svc5, created = WavelengthService.objects.get_or_create(
            name="CWDM-1350-Planned",
            defaults={
                "status": "planned",
                "wavelength_nm": east_channels[4].wavelength_nm,
                "description": "Planned service, channel reserved but not yet cabled.",
            },
        )
        if created:
            self._tag(svc5, tag)
            self._assign_channels(svc5, [east_channels[4]])
            self.stdout.write(f"  Service: {svc5.name} (PLANNED, 1-hop, {svc5.wavelength_nm}nm)")

    def _assign_channels(self, service, channels):
        from netbox_wdm.models import WavelengthServiceChannelAssignment, WavelengthServiceNode

        for seq, ch in enumerate(channels, start=1):
            WavelengthServiceChannelAssignment.objects.get_or_create(
                service=service,
                channel=ch,
                defaults={"sequence": seq},
            )
            WavelengthServiceNode.objects.get_or_create(
                service=service,
                channel=ch,
            )

    # ================================================================
    # Summary
    # ================================================================

    def _print_summary(self):
        from dcim.models import Cable, Device, DeviceType, Site

        from netbox_wdm.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceNode,
            WdmChannelTemplate,
            WdmDeviceTypeProfile,
            WdmLinePort,
            WdmNode,
        )

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"  Sites:              {Site.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  DeviceTypes:        {DeviceType.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Devices:            {Device.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Cables:             {Cable.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  WDM Profiles:       {WdmDeviceTypeProfile.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channel Templates:  {WdmChannelTemplate.objects.count()}")
        self.stdout.write(f"  WDM Nodes:          {WdmNode.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Line Ports:        {WdmLinePort.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channels:           {WavelengthChannel.objects.count()}")
        self.stdout.write(f"  Services:           {WavelengthService.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channel Assigns:    {WavelengthServiceChannelAssignment.objects.count()}")
        self.stdout.write(f"  Service Nodes:      {WavelengthServiceNode.objects.count()}")

        self.stdout.write("\n--- Channel Status Breakdown ---")
        for node in WdmNode.objects.filter(tags__slug=SAMPLE_TAG).select_related("device"):
            total = node.channels.count()
            active = node.channels.filter(status="active").count()
            reserved = node.channels.filter(status="reserved").count()
            available = node.channels.filter(status="available").count()
            self.stdout.write(
                f"  {node.device.name}: {total} total ({active} active, {reserved} reserved, {available} available)"
            )

        self.stdout.write("\n--- Services ---")
        for svc in WavelengthService.objects.filter(tags__slug=SAMPLE_TAG):
            hops = svc.channel_assignments.count()
            self.stdout.write(f"  {svc.name}: {svc.status} ({hops} hops, {svc.wavelength_nm}nm)")

        self.stdout.write("\n--- Cables ---")
        for cable in Cable.objects.filter(tags__slug=SAMPLE_TAG):
            self.stdout.write(f"  {cable.label}")
