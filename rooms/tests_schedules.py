from django.test import TestCase
from django_q.models import Schedule

from rooms.apps import register_schedules

ALL_EXPECTED_SCHEDULES = {
    "rooms.tasks.release_expired_holds",
    "core.ota.tasks.process_ari_outbox",
    "rooms.tasks.auto_complete_bookings",
    "rooms.tasks.award_loyalty_for_completed_stays",
    "core.ota.tasks.nightly_full_sync",
    "core.ota.tasks.poll_booking_feed",
}


class ScheduleRegistrationTests(TestCase):
    def test_all_six_schedules_exist(self):
        register_schedules(sender=None)
        funcs = set(Schedule.objects.values_list("func", flat=True))
        self.assertTrue(ALL_EXPECTED_SCHEDULES <= funcs)
        self.assertEqual(len(ALL_EXPECTED_SCHEDULES.intersection(funcs)), 6)

    def test_registration_is_idempotent(self):
        register_schedules(sender=None)
        register_schedules(sender=None)
        for func in ALL_EXPECTED_SCHEDULES:
            self.assertEqual(Schedule.objects.filter(func=func).count(), 1)
