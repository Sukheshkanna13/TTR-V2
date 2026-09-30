from django.test import TestCase
import uuid
from core.ota.mapping import (
    resolve_property,
    resolve_room_type,
    resolve_rate_plans,
    resolve_default_rate_plan,
    resolve_property_mapping,
)
from core.ota.models import ChannexProperty, ChannexRoomType, ChannexRatePlan
from rooms.models import Property


class ChannexMappingTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(name="Test Property", city="Test City")
        self.channex_property_id = uuid.uuid4()
        self.channex_room_type_id = uuid.uuid4()
        self.channex_rate_plan_id = uuid.uuid4()
        self.channex_rate_plan_id2 = uuid.uuid4()
        
        self.channex_prop = ChannexProperty.objects.create(
            property=self.property,
            channex_property_id=self.channex_property_id,
            is_active=True
        )
        
        self.channex_rt = ChannexRoomType.objects.create(
            property_mapping=self.channex_prop,
            room_type="single",
            channex_room_type_id=self.channex_room_type_id
        )
        
        self.channex_rp = ChannexRatePlan.objects.create(
            room_type_mapping=self.channex_rt,
            name="BAR",
            channex_rate_plan_id=self.channex_rate_plan_id,
            is_default=True
        )

        self.channex_rp2 = ChannexRatePlan.objects.create(
            room_type_mapping=self.channex_rt,
            name="B&B",
            channex_rate_plan_id=self.channex_rate_plan_id2,
            is_default=False
        )

    def test_resolve_property(self):
        self.assertEqual(resolve_property(self.property.id), str(self.channex_property_id))
        self.assertIsNone(resolve_property(None))
        self.assertIsNone(resolve_property(uuid.uuid4()))

    def test_resolve_property_mapping(self):
        mapping = resolve_property_mapping(self.property.id)
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.id, self.channex_prop.id)
        self.assertIsNone(resolve_property_mapping(None))
        self.assertIsNone(resolve_property_mapping(uuid.uuid4()))

    def test_resolve_room_type(self):
        self.assertEqual(resolve_room_type(self.property.id, "single"), str(self.channex_room_type_id))
        self.assertIsNone(resolve_room_type(self.property.id, "double"))
        self.assertIsNone(resolve_room_type(None, "single"))
        self.assertIsNone(resolve_room_type(uuid.uuid4(), "single"))

    def test_resolve_rate_plans(self):
        plans = resolve_rate_plans(self.property.id, "single")
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0].channex_rate_plan_id, self.channex_rate_plan_id)
        self.assertEqual(plans[1].channex_rate_plan_id, self.channex_rate_plan_id2)
        
        self.assertEqual(resolve_rate_plans(self.property.id, "double"), [])
        self.assertEqual(resolve_rate_plans(None, "single"), [])
        self.assertEqual(resolve_rate_plans(uuid.uuid4(), "single"), [])

    def test_resolve_default_rate_plan(self):
        plan = resolve_default_rate_plan(self.property.id, "single")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.channex_rate_plan_id, self.channex_rate_plan_id)
        
        self.assertIsNone(resolve_default_rate_plan(self.property.id, "double"))
        self.assertIsNone(resolve_default_rate_plan(None, "single"))
        self.assertIsNone(resolve_default_rate_plan(uuid.uuid4(), "single"))

    def test_inactive_property_mapping(self):
        self.channex_prop.is_active = False
        self.channex_prop.save()

        self.assertIsNone(resolve_property(self.property.id))
        self.assertIsNone(resolve_property_mapping(self.property.id))
        self.assertIsNone(resolve_room_type(self.property.id, "single"))
        self.assertEqual(resolve_rate_plans(self.property.id, "single"), [])
        self.assertIsNone(resolve_default_rate_plan(self.property.id, "single"))
