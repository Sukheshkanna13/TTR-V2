from django.test import TestCase
from django_q.models import Schedule

from rooms.apps import register_schedules

EXPECTED = {
    "rooms.tasks.release_expired_holds",
    "rooms.tasks.auto_complete_bookings",
    "rooms.tasks.award_loyalty_for_completed_stays",
}


class ScheduleRegistrationTests(TestCase):
    def test_schedules_exist_after_migrate(self):
        funcs = set(Schedule.objects.values_list("func", flat=True))
        self.assertTrue(EXPECTED <= funcs)

    def test_registration_is_idempotent(self):
        register_schedules(sender=None)
        register_schedules(sender=None)
        for func in EXPECTED:
            self.assertEqual(Schedule.objects.filter(func=func).count(), 1)
