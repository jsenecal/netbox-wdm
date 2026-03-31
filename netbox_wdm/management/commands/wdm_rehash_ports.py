"""Recompute port sync hashes for WDM nodes.

Usage:
    cd /opt/netbox/netbox
    python manage.py wdm_rehash_ports
    python manage.py wdm_rehash_ports --missing-only
"""

from django.core.management.base import BaseCommand

from netbox_wdm.models import WdmNode
from netbox_wdm.port_sync import check_port_sync, compute_expected_port_hash


class Command(BaseCommand):
    help = "Recompute port sync hashes for WDM nodes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only compute hashes for nodes with an empty expected_port_hash.",
        )

    def handle(self, *args, **options):
        missing_only = options["missing_only"]

        nodes = WdmNode.objects.select_related("device").all()
        if missing_only:
            nodes = nodes.filter(expected_port_hash="")

        total = nodes.count()
        if total == 0:
            self.stdout.write("No nodes to process.")
            return

        self.stdout.write(f"Processing {total} node(s)...")

        updated = 0
        out_of_sync = 0
        for node in nodes:
            expected = compute_expected_port_hash(node)
            in_sync = check_port_sync(node)
            WdmNode.objects.filter(pk=node.pk).update(
                expected_port_hash=expected,
                port_sync_valid=in_sync,
            )
            updated += 1
            if not in_sync:
                out_of_sync += 1
                self.stdout.write(self.style.WARNING(f"  {node} — out of sync"))

        self.stdout.write(f"\nUpdated {updated} node(s). {out_of_sync} out of sync.")
