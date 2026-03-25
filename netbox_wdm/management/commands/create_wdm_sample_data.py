"""Create comprehensive sample data for the netbox-wdm plugin.

Usage:
    cd /opt/netbox/netbox
    python manage.py create_wdm_sample_data
    python manage.py create_wdm_sample_data --flush   # remove sample data first
"""

from django.core.management.base import BaseCommand
from django.db import transaction

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
        role_mux, role_roadm, role_amp = self._create_device_roles(tag)

        # -- DeviceTypes with port templates --
        dt_mux_100g = self._create_mux_device_type(manufacturer, tag, "WDM-MUX-44", "wdm-mux-44", "dwdm_100ghz")
        dt_mux_50g = self._create_mux_device_type(manufacturer, tag, "WDM-MUX-88", "wdm-mux-88", "dwdm_50ghz")
        dt_roadm = self._create_roadm_device_type(manufacturer, tag)
        dt_amp = self._create_amp_device_type(manufacturer, tag)
        dt_cwdm = self._create_cwdm_device_type(manufacturer, tag)

        # -- WDM Profiles on DeviceTypes --
        self._create_profiles(tag, dt_mux_100g, dt_mux_50g, dt_roadm, dt_amp, dt_cwdm)

        # -- Channel templates --
        self._create_channel_templates(tag, dt_mux_100g, dt_mux_50g, dt_roadm, dt_cwdm)

        # -- Devices (auto-creates WdmNodes + WavelengthChannels via signal + save) --
        dev_east_mux = self._create_device("EAST-MUX-01", site_east, dt_mux_100g, role_mux, tag)
        dev_west_mux = self._create_device("WEST-MUX-01", site_west, dt_mux_100g, role_mux, tag)
        dev_hub_roadm = self._create_device("HUB-ROADM-01", site_hub, dt_roadm, role_roadm, tag)
        self._create_device("HUB-AMP-01", site_hub, dt_amp, role_amp, tag)
        dev_east_cwdm = self._create_device("EAST-CWDM-01", site_east, dt_cwdm, role_mux, tag)
        dev_west_50g = self._create_device("WEST-MUX-50G-01", site_west, dt_mux_50g, role_mux, tag)

        # -- Trunk ports --
        self._create_trunk_ports(tag, dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm, dev_west_50g)

        # -- Manually set some channel statuses and port assignments --
        self._configure_channels(dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm)

        # -- Wavelength services in various lifecycle states --
        self._create_services(tag, dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm)

        self.stdout.write(self.style.SUCCESS("\nSample data created successfully."))
        self._print_summary()

    def _flush(self):
        from extras.models import Tag

        from netbox_wdm.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceNode,
            WdmChannelTemplate,
            WdmDeviceTypeProfile,
            WdmNode,
            WdmTrunkPort,
        )

        self.stdout.write("Flushing existing sample data...")

        try:
            tag = Tag.objects.get(slug=SAMPLE_TAG)
        except Tag.DoesNotExist:
            self.stdout.write("  No sample data tag found, nothing to flush.")
            return

        # Delete in dependency order
        WavelengthServiceNode.objects.filter(service__tags=tag).delete()
        WavelengthServiceChannelAssignment.objects.filter(service__tags=tag).delete()
        WavelengthService.objects.filter(tags=tag).delete()
        WavelengthChannel.objects.filter(wdm_node__tags=tag).delete()
        WdmTrunkPort.objects.filter(wdm_node__tags=tag).delete()
        WdmNode.objects.filter(tags=tag).delete()
        WdmChannelTemplate.objects.filter(profile__tags=tag).delete()
        WdmDeviceTypeProfile.objects.filter(tags=tag).delete()

        from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site

        Device.objects.filter(tags=tag).delete()
        DeviceType.objects.filter(tags=tag).delete()
        DeviceRole.objects.filter(tags=tag).delete()
        Manufacturer.objects.filter(tags=tag).delete()
        Site.objects.filter(tags=tag).delete()

        self.stdout.write(self.style.SUCCESS("  Flushed."))

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

    # ---- DCIM Foundation ----

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
        ]:
            role, _ = DeviceRole.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "color": color},
            )
            self._tag(role, tag)
            roles.append(role)
            self.stdout.write(f"  Role: {name}")
        return roles

    # ---- DeviceType creation with port templates ----

    def _create_port_templates(self, dt, num_client_ports, trunk_label="TRUNK"):
        """Create front/rear port templates on a DeviceType."""
        from dcim.models import FrontPortTemplate, RearPortTemplate

        # Trunk rear port (multi-position for WDM mux)
        trunk_rp, _ = RearPortTemplate.objects.get_or_create(
            device_type=dt,
            name=trunk_label,
            defaults={"type": "lc-apc", "positions": num_client_ports},
        )

        # Client front ports
        fps = []
        for i in range(1, num_client_ports + 1):
            fp, _ = FrontPortTemplate.objects.get_or_create(
                device_type=dt,
                name=f"Client-{i:02d}",
                defaults={"type": "lc-upc"},
            )
            fps.append(fp)

        return trunk_rp, fps

    def _create_mux_device_type(self, manufacturer, tag, model, slug, grid):
        from dcim.models import DeviceType

        num_ports = 44 if grid == "dwdm_100ghz" else 88
        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug=slug,
            defaults={"model": model, "u_height": 1},
        )
        self._tag(dt, tag)
        self._create_port_templates(dt, num_ports)
        self.stdout.write(f"  DeviceType: {model} ({num_ports} client ports)")
        return dt

    def _create_roadm_device_type(self, manufacturer, tag):
        from dcim.models import DeviceType, FrontPortTemplate, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="wdm-roadm-2d",
            defaults={"model": "WDM-ROADM-2D", "u_height": 2},
        )
        self._tag(dt, tag)

        # ROADM has two trunk ports (east/west) and 20 add/drop client ports
        for trunk_name in ("TRUNK-EAST", "TRUNK-WEST"):
            RearPortTemplate.objects.get_or_create(
                device_type=dt,
                name=trunk_name,
                defaults={"type": "lc-apc", "positions": 44},
            )
        for i in range(1, 21):
            FrontPortTemplate.objects.get_or_create(
                device_type=dt,
                name=f"AddDrop-{i:02d}",
                defaults={"type": "lc-upc"},
            )
        self.stdout.write("  DeviceType: WDM-ROADM-2D (2 trunks, 20 add/drop)")
        return dt

    def _create_amp_device_type(self, manufacturer, tag):
        from dcim.models import DeviceType, RearPortTemplate

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="wdm-edfa-1ru",
            defaults={"model": "WDM-EDFA-1RU", "u_height": 1},
        )
        self._tag(dt, tag)

        # Amplifier: line-in and line-out rear ports, no front ports
        for name in ("LINE-IN", "LINE-OUT"):
            RearPortTemplate.objects.get_or_create(
                device_type=dt,
                name=name,
                defaults={"type": "lc-apc", "positions": 1},
            )
        self.stdout.write("  DeviceType: WDM-EDFA-1RU (amplifier, no client ports)")
        return dt

    def _create_cwdm_device_type(self, manufacturer, tag):
        from dcim.models import DeviceType

        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            slug="cwdm-mux-18",
            defaults={"model": "CWDM-MUX-18", "u_height": 1},
        )
        self._tag(dt, tag)
        self._create_port_templates(dt, 18)
        self.stdout.write("  DeviceType: CWDM-MUX-18 (18 client ports)")
        return dt

    # ---- WDM Profiles ----

    def _create_profiles(self, tag, dt_mux_100g, dt_mux_50g, dt_roadm, dt_amp, dt_cwdm):
        from netbox_wdm.models import WdmDeviceTypeProfile

        profiles = [
            (dt_mux_100g, "terminal_mux", "dwdm_100ghz"),
            (dt_mux_50g, "terminal_mux", "dwdm_50ghz"),
            (dt_roadm, "roadm", "dwdm_100ghz"),
            (dt_amp, "amplifier", "dwdm_100ghz"),
            (dt_cwdm, "terminal_mux", "cwdm"),
        ]
        for dt, node_type, grid in profiles:
            p, _ = WdmDeviceTypeProfile.objects.get_or_create(
                device_type=dt,
                defaults={"node_type": node_type, "grid": grid},
            )
            self._tag(p, tag)
            self.stdout.write(f"  Profile: {dt.model} -> {node_type}/{grid}")

    # ---- Channel Templates ----

    def _create_channel_templates(self, tag, dt_mux_100g, dt_mux_50g, dt_roadm, dt_cwdm):
        from dcim.models import FrontPortTemplate

        from netbox_wdm.models import WdmChannelTemplate, WdmDeviceTypeProfile
        from netbox_wdm.wdm_constants import WDM_GRIDS

        configs = [
            (dt_mux_100g, "dwdm_100ghz"),
            (dt_mux_50g, "dwdm_50ghz"),
            (dt_roadm, "dwdm_100ghz"),
            (dt_cwdm, "cwdm"),
        ]

        for dt, grid_key in configs:
            profile = WdmDeviceTypeProfile.objects.get(device_type=dt)
            channels_data = WDM_GRIDS[grid_key]
            fp_templates = {fp.name: fp for fp in FrontPortTemplate.objects.filter(device_type=dt)}

            created = 0
            for pos, label, wavelength in channels_data:
                # Match front port template by position
                fp_name = f"Client-{pos:02d}" if f"Client-{pos:02d}" in fp_templates else None
                if fp_name is None:
                    fp_name = f"AddDrop-{pos:02d}" if f"AddDrop-{pos:02d}" in fp_templates else None

                fp_template = fp_templates.get(fp_name) if fp_name else None

                _, was_created = WdmChannelTemplate.objects.get_or_create(
                    profile=profile,
                    grid_position=pos,
                    defaults={
                        "wavelength_nm": wavelength,
                        "label": label,
                        "front_port_template": fp_template,
                    },
                )
                if was_created:
                    created += 1

            self.stdout.write(f"  Channel templates: {dt.model} - {created} channels from {grid_key} grid")

    # ---- Devices ----

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
                # Refresh to pick up the new relation
                dev.refresh_from_db()
            except WdmDeviceTypeProfile.DoesNotExist:
                pass
        else:
            self._tag(dev.wdm_node, tag)

        action = "Created" if created else "Exists"
        channel_count = dev.wdm_node.channels.count() if hasattr(dev, "wdm_node") else 0
        self.stdout.write(f"  {action} device: {name} ({channel_count} channels auto-populated)")
        return dev

    # ---- Trunk Ports ----

    def _create_trunk_ports(self, tag, dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm, dev_west_50g):
        from dcim.models import RearPort

        from netbox_wdm.models import WdmTrunkPort

        # Terminal muxes: single common trunk
        for dev, direction in [
            (dev_east_mux, "common"),
            (dev_west_mux, "common"),
            (dev_east_cwdm, "common"),
            (dev_west_50g, "common"),
        ]:
            rp = RearPort.objects.filter(device=dev).first()
            if rp and hasattr(dev, "wdm_node"):
                tp, created = WdmTrunkPort.objects.get_or_create(
                    wdm_node=dev.wdm_node,
                    rear_port=rp,
                    defaults={"direction": direction, "position": 1},
                )
                if created:
                    self._tag(tp, tag)
                    self.stdout.write(f"  Trunk port: {dev.name} -> {rp.name} ({direction})")

        # ROADM: east and west trunks
        if hasattr(dev_hub_roadm, "wdm_node"):
            for direction, rp_name in [("east", "TRUNK-EAST"), ("west", "TRUNK-WEST")]:
                rp = RearPort.objects.filter(device=dev_hub_roadm, name=rp_name).first()
                if rp:
                    tp, created = WdmTrunkPort.objects.get_or_create(
                        wdm_node=dev_hub_roadm.wdm_node,
                        direction=direction,
                        defaults={"rear_port": rp, "position": 1 if direction == "east" else 2},
                    )
                    if created:
                        self._tag(tp, tag)
                        self.stdout.write(f"  Trunk port: {dev_hub_roadm.name} -> {rp_name} ({direction})")

    # ---- Channel configuration ----

    def _configure_channels(self, dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm):
        from dcim.models import FrontPort

        from netbox_wdm.models import WavelengthChannel

        # Assign front ports to first 10 channels on EAST-MUX-01
        if hasattr(dev_east_mux, "wdm_node"):
            channels = list(dev_east_mux.wdm_node.channels.order_by("grid_position")[:10])
            fps = list(FrontPort.objects.filter(device=dev_east_mux).order_by("name")[:10])
            for ch, fp in zip(channels, fps, strict=True):
                ch.front_port = fp
            WavelengthChannel.objects.bulk_update(channels, ["front_port_id"])
            self.stdout.write(f"  Assigned {len(channels)} front ports on {dev_east_mux.name}")

        # Same for WEST-MUX-01
        if hasattr(dev_west_mux, "wdm_node"):
            channels = list(dev_west_mux.wdm_node.channels.order_by("grid_position")[:10])
            fps = list(FrontPort.objects.filter(device=dev_west_mux).order_by("name")[:10])
            for ch, fp in zip(channels, fps, strict=True):
                ch.front_port = fp
            WavelengthChannel.objects.bulk_update(channels, ["front_port_id"])
            self.stdout.write(f"  Assigned {len(channels)} front ports on {dev_west_mux.name}")

        # Assign first 8 add/drop ports on ROADM
        if hasattr(dev_hub_roadm, "wdm_node"):
            channels = list(dev_hub_roadm.wdm_node.channels.order_by("grid_position")[:8])
            fps = list(FrontPort.objects.filter(device=dev_hub_roadm).order_by("name")[:8])
            for ch, fp in zip(channels, fps, strict=True):
                ch.front_port = fp
            WavelengthChannel.objects.bulk_update(channels, ["front_port_id"])
            self.stdout.write(f"  Assigned {len(channels)} add/drop ports on {dev_hub_roadm.name}")

        # Assign first 6 ports on CWDM
        if hasattr(dev_east_cwdm, "wdm_node"):
            channels = list(dev_east_cwdm.wdm_node.channels.order_by("grid_position")[:6])
            fps = list(FrontPort.objects.filter(device=dev_east_cwdm).order_by("name")[:6])
            for ch, fp in zip(channels, fps, strict=True):
                ch.front_port = fp
            WavelengthChannel.objects.bulk_update(channels, ["front_port_id"])
            self.stdout.write(f"  Assigned {len(channels)} front ports on {dev_east_cwdm.name}")

        # Set channel statuses: lit, reserved, available mix
        self._set_channel_statuses(dev_east_mux, lit=6, reserved=2)
        self._set_channel_statuses(dev_west_mux, lit=6, reserved=2)
        self._set_channel_statuses(dev_hub_roadm, lit=4, reserved=3)
        self._set_channel_statuses(dev_east_cwdm, lit=3, reserved=1)

    def _set_channel_statuses(self, device, lit=0, reserved=0):
        from netbox_wdm.models import WavelengthChannel

        if not hasattr(device, "wdm_node"):
            return

        channels = list(device.wdm_node.channels.order_by("grid_position"))
        to_update = []
        for i, ch in enumerate(channels):
            if i < lit:
                ch.status = "lit"
                to_update.append(ch)
            elif i < lit + reserved:
                ch.status = "reserved"
                to_update.append(ch)

        if to_update:
            WavelengthChannel.objects.bulk_update(to_update, ["status"])
            self.stdout.write(
                f"  Channel status on {device.name}: {lit} lit, {reserved} reserved, "
                f"{len(channels) - lit - reserved} available"
            )

    # ---- Wavelength Services ----

    def _create_services(self, tag, dev_east_mux, dev_west_mux, dev_hub_roadm, dev_east_cwdm):
        from netbox_wdm.models import (
            WavelengthService,
        )

        east_channels = (
            list(dev_east_mux.wdm_node.channels.order_by("grid_position")) if hasattr(dev_east_mux, "wdm_node") else []
        )
        west_channels = (
            list(dev_west_mux.wdm_node.channels.order_by("grid_position")) if hasattr(dev_west_mux, "wdm_node") else []
        )
        hub_channels = (
            list(dev_hub_roadm.wdm_node.channels.order_by("grid_position"))
            if hasattr(dev_hub_roadm, "wdm_node")
            else []
        )
        cwdm_channels = (
            list(dev_east_cwdm.wdm_node.channels.order_by("grid_position"))
            if hasattr(dev_east_cwdm, "wdm_node")
            else []
        )

        if not east_channels or not west_channels:
            self.stdout.write(self.style.WARNING("  Skipping services: missing channels"))
            return

        # Service 1: ACTIVE end-to-end service (East -> Hub -> West) on channel 1
        svc1, created = WavelengthService.objects.get_or_create(
            name="Lambda-C21-EastWest",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[0].wavelength_nm,
                "description": "Production wavelength service from East Coast to West Coast via Central Hub.",
            },
        )
        if created:
            self._tag(svc1, tag)
            self._assign_channels(svc1, [east_channels[0], hub_channels[0], west_channels[0]])
            self.stdout.write(f"  Service: {svc1.name} (ACTIVE, 3-hop E2E)")

        # Service 2: ACTIVE direct service (East -> West) on channel 2
        svc2, created = WavelengthService.objects.get_or_create(
            name="Lambda-C22-Direct",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[1].wavelength_nm,
                "description": "Direct point-to-point wavelength between East and West.",
            },
        )
        if created:
            self._tag(svc2, tag)
            self._assign_channels(svc2, [east_channels[1], west_channels[1]])
            self.stdout.write(f"  Service: {svc2.name} (ACTIVE, 2-hop direct)")

        # Service 3: ACTIVE service on channel 3
        svc3, created = WavelengthService.objects.get_or_create(
            name="Lambda-C23-Metro",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[2].wavelength_nm,
                "description": "Metro ring wavelength via hub ROADM.",
            },
        )
        if created:
            self._tag(svc3, tag)
            self._assign_channels(svc3, [east_channels[2], hub_channels[2], west_channels[2]])
            self.stdout.write(f"  Service: {svc3.name} (ACTIVE, 3-hop metro)")

        # Service 4: PLANNED service on channel 4 (not yet lit)
        svc4, created = WavelengthService.objects.get_or_create(
            name="Lambda-C24-Planned",
            defaults={
                "status": "planned",
                "wavelength_nm": east_channels[3].wavelength_nm,
                "description": "Planned expansion wavelength, pending fiber turn-up.",
            },
        )
        if created:
            self._tag(svc4, tag)
            self._assign_channels(svc4, [east_channels[3], west_channels[3]])
            self.stdout.write(f"  Service: {svc4.name} (PLANNED, 2-hop)")

        # Service 5: STAGED service on channel 5 (reserved, not active yet)
        svc5, created = WavelengthService.objects.get_or_create(
            name="Lambda-C25-Staged",
            defaults={
                "status": "staged",
                "wavelength_nm": east_channels[4].wavelength_nm,
                "description": "Staged for customer turn-up next maintenance window.",
            },
        )
        if created:
            self._tag(svc5, tag)
            self._assign_channels(svc5, [east_channels[4], hub_channels[4], west_channels[4]])
            self.stdout.write(f"  Service: {svc5.name} (STAGED, 3-hop)")

        # Service 6: DECOMMISSIONED service on channel 6
        svc6, created = WavelengthService.objects.get_or_create(
            name="Lambda-C26-Decom",
            defaults={
                "status": "planned",
                "wavelength_nm": east_channels[5].wavelength_nm,
                "description": "Previously active wavelength, now decommissioned.",
            },
        )
        if created:
            self._tag(svc6, tag)
            self._assign_channels(svc6, [east_channels[5], west_channels[5]])
            # Transition to decommissioned to trigger lifecycle side effects
            svc6.status = "decommissioned"
            svc6.save()
            self.stdout.write(f"  Service: {svc6.name} (DECOMMISSIONED, lifecycle tested)")

        # Service 7: CWDM service (different grid)
        if cwdm_channels:
            svc7, created = WavelengthService.objects.get_or_create(
                name="CWDM-1310-Local",
                defaults={
                    "status": "active",
                    "wavelength_nm": cwdm_channels[2].wavelength_nm,
                    "description": "Local CWDM service on 1310nm channel.",
                },
            )
            if created:
                self._tag(svc7, tag)
                self._assign_channels(svc7, [cwdm_channels[2]])
                self.stdout.write(f"  Service: {svc7.name} (ACTIVE, CWDM single-hop)")

        # Service 8: Multi-hop through hub with all 3 nodes
        svc8, created = WavelengthService.objects.get_or_create(
            name="Lambda-C27-FullPath",
            defaults={
                "status": "active",
                "wavelength_nm": east_channels[6].wavelength_nm
                if len(east_channels) > 6
                else east_channels[0].wavelength_nm,
                "description": "Full east-to-west path demonstrating 3-node stitched trace.",
            },
        )
        if created and len(east_channels) > 6 and len(hub_channels) > 6 and len(west_channels) > 6:
            self._tag(svc8, tag)
            # Ensure channel 7 is lit on all nodes for this service
            for ch in [east_channels[6], hub_channels[6], west_channels[6]]:
                if ch.status == "available":
                    ch.status = "lit"
                    ch.save()
            self._assign_channels(svc8, [east_channels[6], hub_channels[6], west_channels[6]])
            self.stdout.write(f"  Service: {svc8.name} (ACTIVE, full 3-node stitch)")

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

    # ---- Summary ----

    def _print_summary(self):
        from dcim.models import Device, DeviceType, Site

        from netbox_wdm.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceNode,
            WdmChannelTemplate,
            WdmDeviceTypeProfile,
            WdmNode,
            WdmTrunkPort,
        )

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"  Sites:              {Site.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  DeviceTypes:        {DeviceType.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Devices:            {Device.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  WDM Profiles:       {WdmDeviceTypeProfile.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channel Templates:  {WdmChannelTemplate.objects.count()}")
        self.stdout.write(f"  WDM Nodes:          {WdmNode.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Trunk Ports:        {WdmTrunkPort.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channels:           {WavelengthChannel.objects.count()}")
        self.stdout.write(f"  Services:           {WavelengthService.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channel Assigns:    {WavelengthServiceChannelAssignment.objects.count()}")
        self.stdout.write(f"  Service Nodes:      {WavelengthServiceNode.objects.count()}")

        self.stdout.write("\n--- Channel Status Breakdown ---")
        for node in WdmNode.objects.filter(tags__slug=SAMPLE_TAG).select_related("device"):
            total = node.channels.count()
            lit = node.channels.filter(status="lit").count()
            reserved = node.channels.filter(status="reserved").count()
            available = node.channels.filter(status="available").count()
            self.stdout.write(
                f"  {node.device.name}: {total} total ({lit} lit, {reserved} reserved, {available} available)"
            )

        self.stdout.write("\n--- Services ---")
        for svc in WavelengthService.objects.filter(tags__slug=SAMPLE_TAG):
            hops = svc.channel_assignments.count()
            self.stdout.write(f"  {svc.name}: {svc.status} ({hops} hops, {svc.wavelength_nm}nm)")
