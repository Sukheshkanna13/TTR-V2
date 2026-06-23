import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import Cause, Attraction


class Command(BaseCommand):
    help = "Seeds the database with sample causes and events/attractions."

    def handle(self, *args, **options):
        # 1. Seed Causes if none exist
        if not Cause.objects.exists():
            causes_data = [
                {
                    "title": "Sandalwood restoration",
                    "location": "KARNATAKA",
                    "description": "Replanting native sandalwood with Forest Dept.",
                    "target_amount": Decimal("1000000.00"),
                    "raised_amount": Decimal("420000.00"),
                    "sort_order": 1,
                },
                {
                    "title": "Pondicherry coastal cleanup",
                    "location": "TAMIL NADU",
                    "description": "Weekly beach cleans and turtle hatchery support.",
                    "target_amount": Decimal("600000.00"),
                    "raised_amount": Decimal("280000.00"),
                    "sort_order": 2,
                },
                {
                    "title": "Artisan grants",
                    "location": "PAN-INDIA",
                    "description": "Direct grants to potters, weavers, brassworkers.",
                    "target_amount": Decimal("800000.00"),
                    "raised_amount": Decimal("510000.00"),
                    "sort_order": 3,
                }
            ]
            for cdata in causes_data:
                Cause.objects.create(**cdata)
            self.stdout.write(self.style.SUCCESS("Successfully seeded sample causes."))
        else:
            self.stdout.write(self.style.WARNING("Causes already exist. Skipping Cause seeding."))

        # 2. Seed Attractions/Events if none exist
        if not Attraction.objects.exists():
            attractions_data = [
                {
                    "city": "Pondicherry",
                    "name": "Promenade Beach Clean & Sea Turtle Hatchery Walk",
                    "category": "EVENT",
                    "description": "Join our weekly early-morning community coastal walk. Help clean the coastline and learn about turtle conservation.",
                    "address": "Promenade Beach, White Town",
                    "opening_hrs": "Saturdays, 6:00 AM - 8:00 AM",
                    "is_visible": True,
                    "sort_order": 1,
                },
                {
                    "city": "Near Auroville",
                    "name": "Terracotta & Pottery Workshop",
                    "category": "EVENT",
                    "description": "Experience local terracotta pottery making with master craftsmen. Shape your own clay and take home a piece of local art.",
                    "address": "Artisan Village, Near Auroville",
                    "opening_hrs": "Daily, 10:00 AM - 12:00 PM & 3:00 PM - 5:00 PM",
                    "is_visible": True,
                    "sort_order": 2,
                },
                {
                    "city": "Pondicherry",
                    "name": "Sri Aurobindo Ashram",
                    "category": "TEMPLE",
                    "description": "A spiritual community established in 1926, offering peace and quiet meditation spaces in the heart of White Town.",
                    "address": "Marine Street, White Town",
                    "opening_hrs": "8:00 AM - 12:00 PM, 2:00 PM - 6:00 PM",
                    "is_visible": True,
                    "sort_order": 3,
                }
            ]
            for adata in attractions_data:
                Attraction.objects.create(**adata)
            self.stdout.write(self.style.SUCCESS("Successfully seeded sample attractions/events."))
        else:
            self.stdout.write(self.style.WARNING("Attractions/Events already exist. Skipping Attraction seeding."))
