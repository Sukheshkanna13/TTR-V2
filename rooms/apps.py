"""
rooms app configuration.
"""

from django.apps import AppConfig


class RoomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rooms"
    verbose_name = "Rooms & Bookings"

    def ready(self):
        try:
            from django_q.models import Schedule
            
            # Register release_expired_holds every 10 minutes
            Schedule.objects.get_or_create(
                func="rooms.tasks.release_expired_holds",
                defaults={
                    "schedule_type": Schedule.MINUTES,
                    "minutes": 10,
                    "repeats": -1
                }
            )
            
            # Register auto_complete_bookings daily
            Schedule.objects.get_or_create(
                func="rooms.tasks.auto_complete_bookings",
                defaults={
                    "schedule_type": Schedule.DAILY,
                    "repeats": -1
                }
            )
        except Exception:
            # Catch exceptions during migrations or initial setup
            pass
