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
            
            # Safety-net sweep every 1 minute. Holds are normally released the
            # instant a guest abandons checkout (ReleaseHoldView / payment-failure
            # paths); this sweep only catches holds whose client never pinged
            # (e.g. crashed tab), keeping inventory accurate for OTA sync.
            Schedule.objects.update_or_create(
                func="rooms.tasks.release_expired_holds",
                defaults={
                    "schedule_type": Schedule.MINUTES,
                    "minutes": 1,
                    "repeats": -1
                }
            )
            
            # Channex ARI outbox: coalesce pending changes and push them,
            # rate-limited and with retry/backoff (core/ota/tasks.py).
            Schedule.objects.update_or_create(
                func="core.ota.tasks.process_ari_outbox",
                defaults={
                    "schedule_type": Schedule.MINUTES,
                    "minutes": 1,
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

            # Credit loyalty points 24h after checkout, hourly sweep so the
            # 24h cutoff is caught promptly rather than once a day.
            Schedule.objects.update_or_create(
                func="rooms.tasks.award_loyalty_for_completed_stays",
                defaults={
                    "schedule_type": Schedule.HOURLY,
                    "repeats": -1
                }
            )

            # C8 — Channex nightly full sync (certification Test 1 / reconciliation).
            # Runs once per day at off-peak hours (2 AM).  Channex rule: full sync
            # ≤ once per 24 h; delta updates (outbox) handle real-time changes.
            Schedule.objects.update_or_create(
                func="core.ota.tasks.nightly_full_sync",
                defaults={
                    "schedule_type": Schedule.DAILY,
                    "repeats": -1,
                }
            )
            # C10 — Channex booking feed poll (backup ingest path).
            # Primary is the webhook; this catches anything the webhook missed.
            Schedule.objects.update_or_create(
                func="core.ota.tasks.poll_booking_feed",
                defaults={
                    "schedule_type": Schedule.MINUTES,
                    "minutes": 15,
                    "repeats": -1,
                }
            )
        except Exception:
            # Catch exceptions during migrations or initial setup
            pass
