"""
rooms app configuration.
"""

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def register_schedules(sender, using=None, **kwargs):
    """
    Register the recurring django-q jobs. Runs once per `migrate` (i.e. once per
    deploy) instead of on every process start, so gunicorn workers, `check`,
    `collectstatic` and `shell` never write to the database and concurrent
    workers cannot race into duplicate Schedule rows.
    """
    try:
        from django_q.models import Schedule

        schedules = Schedule.objects.using(using or "default")

        # Safety-net sweep every 1 minute. Holds are normally released the
        # instant a guest abandons checkout (ReleaseHoldView / payment-failure
        # paths); this sweep only catches holds whose client never pinged
        # (e.g. crashed tab), keeping inventory accurate for OTA sync.
        schedules.update_or_create(
            func="rooms.tasks.release_expired_holds",
            defaults={
                "schedule_type": Schedule.MINUTES,
                "minutes": 1,
                "repeats": -1,
            },
        )

        # Register auto_complete_bookings daily
        schedules.get_or_create(
            func="rooms.tasks.auto_complete_bookings",
            defaults={
                "schedule_type": Schedule.DAILY,
                "repeats": -1,
            },
        )

        # Credit loyalty points 24h after checkout, hourly sweep so the
        # 24h cutoff is caught promptly rather than once a day.
        schedules.update_or_create(
            func="rooms.tasks.award_loyalty_for_completed_stays",
            defaults={
                "schedule_type": Schedule.HOURLY,
                "repeats": -1,
            },
        )
    except Exception:
        # django_q tables may not exist yet (partial migrate); never abort migrate.
        logger.warning("Could not register django-q schedules.", exc_info=True)


class RoomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rooms"
    verbose_name = "Rooms & Bookings"

    def ready(self):
        post_migrate.connect(register_schedules, sender=self)
