"""
Management command to seed the database with sample rooms for testing.
Usage: python manage.py seed_rooms
"""

from django.core.management.base import BaseCommand

from rooms.models import Room


SAMPLE_ROOMS = [
    # Mumbai
    {"name": "Sea View Standard", "city": "Mumbai", "room_type": "single", "price_per_night": 2500, "capacity": 1, "amenities": "WiFi, AC, TV", "description": "Cozy single room with a view of the Arabian Sea."},
    {"name": "City Double Room", "city": "Mumbai", "room_type": "double", "price_per_night": 4500, "capacity": 2, "amenities": "WiFi, AC, TV, Mini Bar", "description": "Spacious double room in the heart of Mumbai."},
    {"name": "Marine Drive Deluxe", "city": "Mumbai", "room_type": "deluxe", "price_per_night": 8500, "capacity": 3, "amenities": "WiFi, AC, TV, Mini Bar, Jacuzzi, Room Service", "description": "Luxury suite overlooking Marine Drive."},
    {"name": "Budget Single", "city": "Mumbai", "room_type": "single", "price_per_night": 1500, "capacity": 1, "amenities": "WiFi, AC", "description": "Affordable single room near the airport."},

    # Delhi
    {"name": "Connaught Place Single", "city": "Delhi", "room_type": "single", "price_per_night": 2000, "capacity": 1, "amenities": "WiFi, AC, TV", "description": "Clean single room in central Delhi."},
    {"name": "Chandni Chowk Double", "city": "Delhi", "room_type": "double", "price_per_night": 3500, "capacity": 2, "amenities": "WiFi, AC, TV, Breakfast", "description": "Comfortable double room with complimentary breakfast."},
    {"name": "Lutyens Deluxe Suite", "city": "Delhi", "room_type": "deluxe", "price_per_night": 12000, "capacity": 4, "amenities": "WiFi, AC, TV, Mini Bar, Pool, Spa, Room Service", "description": "Premium suite in the diplomatic area."},

    # Bangalore
    {"name": "Tech Park Single", "city": "Bangalore", "room_type": "single", "price_per_night": 1800, "capacity": 1, "amenities": "WiFi, AC, TV, Work Desk", "description": "Business-friendly single room near IT corridor."},
    {"name": "MG Road Double", "city": "Bangalore", "room_type": "double", "price_per_night": 3800, "capacity": 2, "amenities": "WiFi, AC, TV, Mini Bar, Breakfast", "description": "Modern double room on MG Road."},
    {"name": "Palace Deluxe", "city": "Bangalore", "room_type": "deluxe", "price_per_night": 7500, "capacity": 3, "amenities": "WiFi, AC, TV, Mini Bar, Pool, Gym", "description": "Elegant deluxe room with palace-style decor."},

    # Goa
    {"name": "Beach Hut Single", "city": "Goa", "room_type": "single", "price_per_night": 2200, "capacity": 1, "amenities": "WiFi, Fan, Beach Access", "description": "Charming beach hut steps from the shore."},
    {"name": "Sunset Double Villa", "city": "Goa", "room_type": "double", "price_per_night": 5000, "capacity": 2, "amenities": "WiFi, AC, TV, Pool, Beach Access", "description": "Beautiful villa with sunset views."},
    {"name": "Luxury Beach Deluxe", "city": "Goa", "room_type": "deluxe", "price_per_night": 9500, "capacity": 4, "amenities": "WiFi, AC, TV, Private Pool, Beach Access, Spa, Room Service", "description": "Ultimate beachfront luxury experience."},

    # Chennai
    {"name": "Marina View Single", "city": "Chennai", "room_type": "single", "price_per_night": 1700, "capacity": 1, "amenities": "WiFi, AC, TV", "description": "Simple room near Marina Beach."},
    {"name": "T Nagar Double", "city": "Chennai", "room_type": "double", "price_per_night": 3200, "capacity": 2, "amenities": "WiFi, AC, TV, Breakfast", "description": "Comfortable room in the shopping district."},
]


class Command(BaseCommand):
    help = "Seeds the database with sample hotel rooms for testing."

    def handle(self, *args, **options):
        if Room.objects.exists():
            self.stdout.write(self.style.WARNING("Rooms already exist. Skipping seed."))
            self.stdout.write(self.style.WARNING("To re-seed, run: python manage.py flush --no-input && python manage.py seed_rooms"))
            return

        rooms = []
        for room_data in SAMPLE_ROOMS:
            rooms.append(Room(**room_data))

        Room.objects.bulk_create(rooms)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {len(rooms)} sample rooms!")
        )

        # Show summary by city
        cities = set(r["city"] for r in SAMPLE_ROOMS)
        for city in sorted(cities):
            count = sum(1 for r in SAMPLE_ROOMS if r["city"] == city)
            self.stdout.write(f"   {city}: {count} rooms")
