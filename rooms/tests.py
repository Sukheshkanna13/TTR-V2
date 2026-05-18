from django.test import TestCase
from rooms.models import Room, Property


class RoomOperationalStatusTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='Test Prop', city='Pondy', is_active=True)
        self.room = Room.objects.create(
            property=self.prop,
            name='R1',
            city='Pondy',
            room_type='single',
            price_per_night=2000,
            capacity=2,
        )

    def test_default_status_is_available(self):
        self.assertEqual(self.room.operational_status, 'available')

    def test_all_four_statuses_accept(self):
        for status in ['available', 'cleaning', 'maintenance', 'out_of_order']:
            self.room.operational_status = status
            self.room.full_clean()
            self.room.save()
            self.assertEqual(Room.objects.get(pk=self.room.pk).operational_status, status)
