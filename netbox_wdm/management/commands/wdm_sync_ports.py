"""Sync WDM node port mappings to match the channel grid.

Usage:
    cd /opt/netbox/netbox
    python manage.py wdm_sync_ports <pk>
    python manage.py wdm_sync_ports <pk> --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from netbox_wdm.models import WdmNode
from netbox_wdm.port_sync import apply_sync, compute_sync_diff


class Command(BaseCommand):
    help = "Sync WDM node port mappings to match the channel grid."

    def add_arguments(self, parser):
        parser.add_argument("pk", type=int, help="Primary key of the WdmNode to sync.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without applying.",
        )

    def handle(self, *args, **options):
        pk = options["pk"]
        dry_run = options["dry_run"]

        try:
            node = WdmNode.objects.select_related("device").get(pk=pk)
        except WdmNode.DoesNotExist as err:
            raise CommandError(f"WdmNode with pk={pk} does not exist.") from err

        self.stdout.write(f"WDM Node: {node} (device: {node.device.name})")
        self.stdout.write(f"Current port_sync_valid: {node.port_sync_valid}")
        self.stdout.write("")

        if dry_run:
            result = compute_sync_diff(node)
            self.stdout.write(self.style.WARNING("DRY RUN — no changes applied."))
        else:
            result = apply_sync(node)

        self._print_report(result, dry_run)

    def _print_report(self, result, dry_run):
        warnings = result["warnings"]
        changes = result["changes"]

        self.stdout.write("")
        self.stdout.write("--- Warnings ---")
        self.stdout.write(f"Cable paths affected: {warnings['cable_paths_affected']}")
        if warnings["wavelength_services"]:
            for svc in warnings["wavelength_services"]:
                self.stdout.write(f"  Wavelength service: {svc['display']} (id={svc['id']})")
        else:
            self.stdout.write("  No wavelength services affected.")

        self.stdout.write("")
        self.stdout.write("--- Changes ---")

        rp_create = changes["rear_ports"]["create"]
        if rp_create:
            self.stdout.write(f"Rear ports to create: {len(rp_create)}")
            for rp in rp_create:
                self.stdout.write(f"  {rp['name']} ({rp['type']}, {rp['positions']} positions)")
        else:
            self.stdout.write("Rear ports to create: 0")

        fp_create = changes["front_ports"]["create"]
        if fp_create:
            self.stdout.write(f"Front ports to create: {len(fp_create)}")
            for fp in fp_create:
                self.stdout.write(f"  {fp['name']} ({fp['type']})")
        else:
            self.stdout.write("Front ports to create: 0")

        pm = changes["port_mappings"]
        verb = "to create" if dry_run else "created"
        self.stdout.write(f"Port mappings {verb}: {pm['create']}")
        verb = "to delete" if dry_run else "deleted"
        self.stdout.write(f"Port mappings {verb}: {pm['delete']}")
