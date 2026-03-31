"""Create sample data for the netbox-wdm plugin using shared topology builders.

Usage:
    cd /opt/netbox/netbox
    python manage.py create_wdm_sample_data
    python manage.py create_wdm_sample_data --flush   # remove sample data first
"""

from django.core.management.base import BaseCommand
from django.db import transaction

SAMPLE_TAG = "wdm-sample-data"


class Command(BaseCommand):
    help = "Create comprehensive WDM sample data."

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
        from netbox_wdm.testing import (
            create_cwdm_mux_dx_type,
            create_cwdm_mux_sf_type,
            create_device_roles,
            create_dwdm_mux_dx_type,
            create_fiber_pp_type,
            create_manufacturer,
            create_roadm_2d_type,
            create_site,
            duplex_mux_pair,
            dwdm_mux_to_roadm,
            sf_mux_pair,
        )

        mfr = create_manufacturer("Acme Photonics")
        site = create_site("WDM-Demo-Site")
        roles = create_device_roles()

        # -- Device types (factories create profiles + channel plans automatically) --
        dt_cwdm_dx = create_cwdm_mux_dx_type(mfr)
        dt_cwdm_sf = create_cwdm_mux_sf_type(mfr)
        dt_dwdm = create_dwdm_mux_dx_type(mfr)
        dt_roadm = create_roadm_2d_type(mfr)
        dt_pp = create_fiber_pp_type(mfr)

        # Tag foundation objects
        for obj in [mfr, site, *roles.values()]:
            self._tag(obj, tag)
        for dt in [dt_cwdm_dx, dt_cwdm_sf, dt_dwdm, dt_roadm, dt_pp]:
            self._tag(dt, tag)
            # Tag associated WDM profile if present
            if hasattr(dt, "wdm_profile"):
                self._tag(dt.wdm_profile, tag)

        # -- Build topologies --
        topo1 = duplex_mux_pair(site, dt_cwdm_dx, dt_pp, roles, name_prefix="CWDM-DX-")
        topo2 = sf_mux_pair(site, dt_cwdm_sf, dt_pp, roles, name_prefix="CWDM-SF-")
        topo3 = dwdm_mux_to_roadm(site, dt_dwdm, dt_roadm, dt_pp, roles, name_prefix="DWDM-")

        # Tag all topology objects
        for topo in [topo1, topo2, topo3]:
            for bundle in topo.bundles.values():
                self._tag(bundle.device, tag)
                self._tag(bundle.node, tag)
                for lp in bundle.line_ports.values():
                    self._tag(lp, tag)
            for pp in topo.patch_panels:
                self._tag(pp, tag)
            for cable in topo.cables:
                self._tag(cable, tag)

        self.stdout.write(f"  Topology 1: {topo1.name} ({len(topo1.cables)} cables)")
        self.stdout.write(f"  Topology 2: {topo2.name} ({len(topo2.cables)} cables)")
        self.stdout.write(f"  Topology 3: {topo3.name} ({len(topo3.cables)} cables)")

        # -- Configure channel statuses --
        self._configure_channel_statuses(topo1)

        # -- Rebuild wavelength paths (signals use on_commit, which won't fire inside atomic) --
        from netbox_wdm.trace import rebuild_wavelength_paths_for_node

        for topo in [topo1, topo2, topo3]:
            for bundle in topo.bundles.values():
                rebuild_wavelength_paths_for_node(bundle.node)

        from netbox_wdm.models import WdmWavelengthPath

        self.stdout.write(f"  Wavelength paths: {WdmWavelengthPath.objects.count()}")

        # -- WDM circuits --
        self._create_circuits(tag, topo1, topo2)

        self.stdout.write(self.style.SUCCESS("\nSample data created successfully."))
        self._print_summary()

    # ================================================================
    # Flush
    # ================================================================

    def _flush(self):
        from extras.models import Tag

        from netbox_wdm.models import (
            WdmChannel,
            WdmChannelPlan,
            WdmCircuit,
            WdmLinePort,
            WdmNode,
            WdmProfile,
            WdmWavelengthPath,
            WdmWavelengthPathChannel,
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
        # M2M wavelength_paths will be auto-cleared when circuits are deleted
        # Delete wavelength path channels and paths for tagged nodes
        WdmWavelengthPathChannel.objects.filter(channel__wdm_node__tags=tag).delete()
        WdmWavelengthPath.objects.filter(path_channels__isnull=True).delete()
        WdmCircuit.objects.filter(tags=tag).delete()
        WdmChannel.objects.filter(wdm_node__tags=tag).delete()
        WdmLinePort.objects.filter(wdm_node__tags=tag).delete()
        WdmNode.objects.filter(tags=tag).delete()
        WdmChannelPlan.objects.filter(profile__tags=tag).delete()
        WdmProfile.objects.filter(tags=tag).delete()

        # Then DCIM objects
        Device.objects.filter(tags=tag).delete()
        DeviceType.objects.filter(tags=tag).delete()
        DeviceRole.objects.filter(tags=tag).delete()
        Manufacturer.objects.filter(tags=tag).delete()
        Site.objects.filter(tags=tag).delete()

        self.stdout.write(self.style.SUCCESS("  Flushed."))

    # ================================================================
    # Tag helpers
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
        if hasattr(obj, "tags"):
            obj.tags.add(tag)

    # ================================================================
    # Channel status configuration
    # ================================================================

    def _configure_channel_statuses(self, topo):
        """Set channel statuses on topo's mux_a to demonstrate all status states."""
        from netbox_wdm.models import WdmChannel

        for key in ("mux_a", "mux_b"):
            bundle = topo.bundles.get(key)
            if not bundle:
                continue

            channels = list(bundle.node.channels.order_by("grid_position"))
            if len(channels) < 5:
                continue

            channels[0].status = "active"
            channels[1].status = "active"
            channels[2].status = "reserved"
            channels[3].status = "active"
            channels[4].status = "reserved"
            WdmChannel.objects.bulk_update(channels[:5], ["status"])
            self.stdout.write(
                f"  Channel status on {bundle.device.name}: "
                f"2 active+connected, 1 reserved+connected, "
                f"1 active+disconnected, 1 reserved+disconnected"
            )

    # ================================================================
    # WDM Circuits
    # ================================================================

    def _create_circuits(self, tag, topo_dx, topo_sf):
        from netbox_wdm.models import WdmChannel, WdmCircuit

        def find_path_from(channel, origin_node):
            """Find the wavelength path that starts from origin_node for this channel's wavelength."""
            from netbox_wdm.models import WdmWavelengthPathChannel

            origin_channel = WdmChannel.objects.filter(
                wdm_node=origin_node, grid_position=channel.grid_position
            ).first()
            if not origin_channel:
                return None
            # Find the path where this origin channel is at sequence 0
            entry = WdmWavelengthPathChannel.objects.filter(
                channel=origin_channel, sequence=0
            ).select_related("path").first()
            return entry.path if entry else None

        def find_tx_rx_pair(channel, node_a, node_b):
            """Find both directional paths for a wavelength: A→B (TX) and B→A (RX from A's perspective)."""
            tx = find_path_from(channel, node_a)
            rx = find_path_from(channel, node_b)
            return tx, rx

        def make_circuit(name, status, paths, tag):
            ckt, created = WdmCircuit.objects.get_or_create(name=name, defaults={"status": status})
            if created:
                ckt.wavelength_paths.add(*[p for p in paths if p])
                self._tag(ckt, tag)
                labels = [p.get_display_label() for p in paths if p]
                self.stdout.write(f"  Circuit: {name} ({status}, {len(labels)} path(s))")
                for lbl in labels:
                    self.stdout.write(f"    {lbl}")

        # -- Duplex mux circuits (TX+RX pairs) --
        dx_a = topo_dx.bundles.get("mux_a")
        dx_b = topo_dx.bundles.get("mux_b")
        if dx_a and dx_b:
            dx_channels = list(dx_a.node.channels.order_by("grid_position"))
            node_a, node_b = dx_a.node, dx_b.node

            # Bidirectional single-wavelength circuits
            bidi_spec = [
                ("CWDM-DX-Active", "active", 0),
                ("CWDM-DX-Staged", "staged", 1),
                ("CWDM-DX-Fault", "active", 2),
                ("CWDM-DX-Planned", "planned", 3),
            ]
            for name, ckt_status, ch_idx in bidi_spec:
                if ch_idx < len(dx_channels):
                    tx, rx = find_tx_rx_pair(dx_channels[ch_idx], node_a, node_b)
                    make_circuit(name, ckt_status, [tx, rx], tag)

            # Multi-path bonded circuit (4 wavelengths, both directions each)
            bonded_paths = []
            for i in range(4, min(8, len(dx_channels))):
                tx, rx = find_tx_rx_pair(dx_channels[i], node_a, node_b)
                if tx:
                    bonded_paths.append(tx)
                if rx:
                    bonded_paths.append(rx)
            if bonded_paths:
                make_circuit("CWDM-DX-4x-Bonded", "active", bonded_paths, tag)

        # -- Single-fiber mux circuits (TX+RX pairs) --
        sf_a = topo_sf.bundles.get("mux_a")
        sf_b = topo_sf.bundles.get("mux_b")
        if sf_a and sf_b:
            sf_channels = list(sf_a.node.channels.order_by("grid_position"))
            sf_node_a, sf_node_b = sf_a.node, sf_b.node
            sf_paths = []
            for i in range(2):
                if i < len(sf_channels):
                    tx, rx = find_tx_rx_pair(sf_channels[i], sf_node_a, sf_node_b)
                    if tx:
                        sf_paths.append(tx)
                    if rx:
                        sf_paths.append(rx)
            if sf_paths:
                make_circuit("CWDM-SF-2x-Bonded", "active", sf_paths, tag)

    # ================================================================
    # Summary
    # ================================================================

    def _print_summary(self):
        from dcim.models import Cable, Device, DeviceType, Site

        from netbox_wdm.models import (
            WdmChannel,
            WdmChannelPlan,
            WdmCircuit,
            WdmLinePort,
            WdmNode,
            WdmProfile,
            WdmWavelengthPath,
        )

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"  Sites:              {Site.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  DeviceTypes:        {DeviceType.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Devices:            {Device.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Cables:             {Cable.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  WDM Profiles:       {WdmProfile.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channel Plans:      {WdmChannelPlan.objects.count()}")
        self.stdout.write(f"  WDM Nodes:          {WdmNode.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Line Ports:         {WdmLinePort.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Channels:           {WdmChannel.objects.count()}")
        self.stdout.write(f"  Circuits:           {WdmCircuit.objects.filter(tags__slug=SAMPLE_TAG).count()}")
        self.stdout.write(f"  Wavelength Paths:   {WdmWavelengthPath.objects.count()}")

        self.stdout.write("\n--- Channel Status Breakdown ---")
        for node in WdmNode.objects.filter(tags__slug=SAMPLE_TAG).select_related("device"):
            total = node.channels.count()
            active = node.channels.filter(status="active").count()
            reserved = node.channels.filter(status="reserved").count()
            available = node.channels.filter(status="available").count()
            self.stdout.write(
                f"  {node.device.name}: {total} total ({active} active, {reserved} reserved, {available} available)"
            )

        self.stdout.write("\n--- Circuits ---")
        for ckt in WdmCircuit.objects.filter(tags__slug=SAMPLE_TAG).prefetch_related("wavelength_paths"):
            paths = list(ckt.wavelength_paths.all())
            if paths:
                wls = ", ".join(str(p.wavelength_nm) for p in paths)
                self.stdout.write(f"  {ckt.name}: {ckt.status} ({len(paths)} path(s): {wls}nm)")
            else:
                self.stdout.write(f"  {ckt.name}: {ckt.status} (no paths)")

        self.stdout.write("\n--- Cables ---")
        for cable in Cable.objects.filter(tags__slug=SAMPLE_TAG):
            self.stdout.write(f"  {cable.label}")
