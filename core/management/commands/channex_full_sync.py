"""
Management command: python manage.py channex_full_sync

Triggers a full 500-day ARI sync to Channex for one or all active properties.
Use this for:
  - Certification Test 1 (run during screenshare to show 2 API calls)
  - Initial load when connecting a new property
  - Manual reconciliation after a long outage

Usage:
    python manage.py channex_full_sync
    python manage.py channex_full_sync --property <property_id>
"""

import json

from django.core.management.base import BaseCommand

from core.ota.tasks import full_sync_property, nightly_full_sync


class Command(BaseCommand):
    help = "Push 500-day full ARI sync to Channex (Test 1 / manual reconciliation)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--property",
            dest="property_id",
            default=None,
            help="UUID or PK of the TTR Property to sync. "
                 "Omit to sync all active Channex-connected properties.",
        )

    def handle(self, *args, **options):
        property_id = options["property_id"]

        if property_id:
            self.stdout.write(f"Starting full sync for property {property_id}...")
            result = full_sync_property(property_id)
            results = {property_id: result}
        else:
            self.stdout.write("Starting full sync for ALL active Channex properties...")
            results = nightly_full_sync()

        # Report
        for pid, res in results.items():
            avail_id = res.get("availability_task_id") or "(none)"
            restr_id = res.get("restrictions_task_id") or "(none)"
            errors = res.get("errors", [])
            room_types = res.get("room_types", [])
            rate_plans = res.get("rate_plans", [])

            if errors:
                self.stdout.write(self.style.ERROR(
                    f"\n[FAIL] Property {pid}\n"
                    f"  Room types:  {room_types}\n"
                    f"  Rate plans:  {rate_plans}\n"
                    f"  Errors:\n" + "\n".join(f"    - {e}" for e in errors)
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\n[OK] Property {pid}\n"
                    f"  Room types:  {room_types}\n"
                    f"  Rate plans:  {rate_plans}\n"
                    f"  Availability task ID : {avail_id}\n"
                    f"  Restrictions task ID : {restr_id}"
                ))

        all_errors = [e for r in results.values() for e in r.get("errors", [])]
        if all_errors:
            raise SystemExit(1)
