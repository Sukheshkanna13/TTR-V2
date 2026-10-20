"""
Regression tests for the Super Admin hardening pass
(docs/ADMIN-PANELS-AUDIT-2026-10-18.md, remediation plan agent C).

Covers: completion guard (C2), revenue statuses (C3), audit codes (H1),
bad input never 500s (H2), cancel -> ARI push + refund note (H5), Channex
pushes on room changes (H6), room validation (H7), analytics maths (M1),
dashboard KPIs (M2), tax bounds (M3), employee_admin management (M6).
"""
import io
import json
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from payments.models import Payment
from rooms.models import Booking, Property, Room
from superadmin.models import AuditLog, PropertyTaxConfig

User = get_user_model()

RECORD_ARI = 'core.ota.dispatch.record_ari_change'


def _user(email, role='guest', **extra):
    user = User.objects.create_user(
        email=email, full_name=extra.pop('full_name', 'Test User'),
        phone=extra.pop('phone', '9999999999'),
        password='testpass123', is_active=True,
    )
    if role is not None:
        UserProfile.objects.create(user=user, role=role)
    return user


def _png_upload(name='x.png'):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), (200, 10, 10)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class HardeningBase(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)
        self.admin = _user('sa-hard@test.com', 'super_admin')
        self.client.force_login(self.admin)
        self.prop = Property.objects.create(
            name='Hard Prop', city='Pondicherry', address='1 Beach Rd', is_active=True)
        self.room = Room.objects.create(
            property=self.prop, name='R1', city='Pondicherry', room_type='single',
            price_per_night=Decimal('1000'), capacity=2)
        self.guest = _user('guest-hard@test.com', 'guest')

    def booking(self, check_in, check_out, status='confirmed', price='1000', room=None):
        return Booking.objects.create(
            user=self.guest, room=room or self.room, check_in=check_in,
            check_out=check_out, status=status, total_price=Decimal(price), guests=1,
        )

    def post_json(self, url, payload, **kw):
        return self.client.post(url, data=json.dumps(payload),
                                content_type='application/json', **kw)

    def last_audit(self, action):
        return AuditLog.objects.filter(action=action).order_by('-created_at').first()


# ── C2 ────────────────────────────────────────────────────────────────────────

class BookingCompleteTest(HardeningBase):
    def test_complete_future_booking_returns_400(self):
        today = timezone.localdate()
        b = self.booking(today + timedelta(days=5), today + timedelta(days=7))
        res = self.client.post(reverse('superadmin:booking-complete', args=[b.pk]))
        self.assertEqual(res.status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.status, 'confirmed')

    def test_complete_past_booking_ok(self):
        today = timezone.localdate()
        b = self.booking(today - timedelta(days=3), today - timedelta(days=1))
        res = self.client.post(reverse('superadmin:booking-complete', args=[b.pk]))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'completed')
        self.assertIsNotNone(self.last_audit('BOOKING_COMPLETED'))

    def test_complete_in_progress_shortens_checkout(self):
        today = timezone.localdate()
        b = self.booking(today - timedelta(days=1), today + timedelta(days=3))
        with mock.patch(RECORD_ARI) as ari:
            res = self.client.post(reverse('superadmin:booking-complete', args=[b.pk]))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'completed')
        self.assertEqual(b.check_out, today)
        ari.assert_called_once()


# ── C3 / M1 analytics ─────────────────────────────────────────────────────────

class AnalyticsTest(HardeningBase):
    def _row(self, res, name='Hard Prop'):
        return next(r for r in res.context['occupancy_by_property'] if r['name'] == name)

    def test_analytics_includes_completed_revenue_and_counts(self):
        today = timezone.localdate()
        self.booking(today, today + timedelta(days=1), 'confirmed', '1000')
        self.booking(today, today + timedelta(days=1), 'completed', '2500')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': today.isoformat(), 'to': today.isoformat()})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_revenue'], Decimal('3500'))
        self.assertEqual(res.context['total_bookings'], 2)
        row = self._row(res)
        self.assertEqual(row['revenue'], Decimal('3500'))
        self.assertEqual(row['count'], 2)

    def test_cancellation_rate_counts_completed_in_denominator(self):
        today = timezone.localdate()
        self.booking(today, today + timedelta(days=1), 'completed')
        self.booking(today, today + timedelta(days=1), 'confirmed')
        self.booking(today, today + timedelta(days=1), 'confirmed')
        self.booking(today, today + timedelta(days=1), 'cancelled')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': today.isoformat(), 'to': today.isoformat()})
        self.assertEqual(res.context['cancellation_rate'], 25.0)

    def test_dashboard_month_revenue_includes_completed(self):
        today = timezone.localdate()
        self.booking(today, today + timedelta(days=1), 'completed', '4200')
        res = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(res.context['month_revenue'], Decimal('4200'))

    def test_occupancy_clips_nights_to_range(self):
        # Range 10..19 March = 10 days, 1 active room = 10 room-nights.
        # Booking 8..12 March overlaps 10, 11 -> 2 nights -> 20%.
        self.booking(date(2026, 3, 8), date(2026, 3, 12), 'confirmed')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': '2026-03-10', 'to': '2026-03-19'})
        self.assertEqual(self._row(res)['occupancy'], 20.0)

    def test_occupancy_counts_booking_spanning_whole_range(self):
        self.booking(date(2026, 2, 20), date(2026, 4, 20), 'completed')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': '2026-03-10', 'to': '2026-03-19'})
        self.assertEqual(self._row(res)['occupancy'], 100.0)

    def test_range_is_inclusive_day_count(self):
        # 2 day range (10th and 11th), one 1-night stay -> 1/2 = 50%
        self.booking(date(2026, 3, 10), date(2026, 3, 11), 'confirmed')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': '2026-03-10', 'to': '2026-03-11'})
        self.assertEqual(self._row(res)['occupancy'], 50.0)

    def test_from_after_to_is_swapped(self):
        self.booking(date(2026, 3, 10), date(2026, 3, 11), 'confirmed')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': '2026-03-11', 'to': '2026-03-10'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['date_from'], date(2026, 3, 10))
        self.assertEqual(res.context['date_to'], date(2026, 3, 11))
        self.assertTrue(res.context['range_swapped'])

    def test_property_with_no_active_rooms_has_zero_occupancy(self):
        self.room.is_active = False
        self.room.save(update_fields=['is_active'])
        self.booking(date(2026, 3, 10), date(2026, 3, 12), 'confirmed')
        res = self.client.get(reverse('superadmin:analytics'),
                              {'from': '2026-03-10', 'to': '2026-03-19'})
        self.assertEqual(self._row(res)['occupancy'], 0)

    def test_bad_date_params_do_not_500(self):
        res = self.client.get(reverse('superadmin:analytics'), {'from': 'zzz', 'to': '2026-99-99'})
        self.assertEqual(res.status_code, 200)


# ── M2 dashboard KPIs ─────────────────────────────────────────────────────────

class DashboardKpiTest(HardeningBase):
    def _payment(self, booking, amount, status='captured', days_ago=0):
        p = Payment.objects.create(
            booking=booking, amount=Decimal(amount), status=status,
            payment_method=Payment.METHOD_CASH)
        if days_ago:
            Payment.objects.filter(pk=p.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago))
        return p

    def test_total_rooms_counts_active_only(self):
        Room.objects.create(
            property=self.prop, name='R2', city='Pondicherry', room_type='double',
            price_per_night=Decimal('2000'), capacity=2, is_active=False)
        res = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(res.context['total_rooms'], 1)

    def test_today_revenue_is_captured_payments_created_today(self):
        far = timezone.localdate() + timedelta(days=30)
        b = self.booking(far, far + timedelta(days=1), 'confirmed', '9999')
        self._payment(b, '700')
        self._payment(b, '300')
        self._payment(b, '5000', status='failed')
        self._payment(b, '4000', days_ago=2)
        res = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(res.context['today_revenue'], Decimal('1000'))
        live = self.client.get(reverse('superadmin:dashboard-live')).json()
        self.assertAlmostEqual(live['today_revenue'], 1000.0)


# ── H1 audit codes ────────────────────────────────────────────────────────────

class AuditCodeTest(HardeningBase):
    def test_walk_in_logs_walk_in_code(self):
        today = timezone.localdate()
        res = self.client.post(reverse('superadmin:walk-in-booking-create'), {
            'room_id': str(self.room.pk),
            'check_in': (today + timedelta(days=10)).isoformat(),
            'check_out': (today + timedelta(days=11)).isoformat(),
            'guest_name': 'Walky', 'guest_phone': '9000000001',
            'guests': 1, 'payment_method': 'cash',
        })
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNotNone(self.last_audit('WALK_IN_BOOKING_CREATED'))
        self.assertFalse(AuditLog.objects.filter(action='BOOKING_COMPLETED').exists())

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_banner_create_toggle_delete_codes(self):
        from core.models import SiteBanner
        res = self.client.post(reverse('superadmin:banner-create'), {
            'title': 'Hello', 'target_page': 'home', 'sort_order': '1',
            'image': _png_upload(),
        })
        self.assertEqual(res.status_code, 302)
        banner = SiteBanner.objects.get(title='Hello')
        self.assertIsNotNone(self.last_audit('BANNER_CREATED'))
        self.assertFalse(AuditLog.objects.filter(action='PROPERTY_UPDATED').exists())

        self.client.post(reverse('superadmin:banner-toggle', args=[banner.pk]))
        self.assertIsNotNone(self.last_audit('BANNER_UPDATED'))

        self.client.post(reverse('superadmin:banner-delete', args=[banner.pk]))
        self.assertIsNotNone(self.last_audit('BANNER_DELETED'))

    def test_room_image_set_primary_code(self):
        from rooms.models import RoomImage
        img = RoomImage.objects.create(room=self.room, image='rooms/x.jpg')
        res = self.client.post(reverse('superadmin:room-image-set-primary', args=[img.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(self.last_audit('ROOM_IMAGE_PRIMARY_SET'))

    def test_event_image_set_primary_code(self):
        from core.models import Attraction, AttractionPhoto
        ev = Attraction.objects.create(name='Ev', city='Pondicherry', category='EVENT')
        img = AttractionPhoto.objects.create(attraction=ev, image='a/x.jpg')
        res = self.client.post(reverse('superadmin:event-image-set-primary', args=[img.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(self.last_audit('EVENT_IMAGE_PRIMARY_SET'))

    def test_loyalty_config_tier_campaign_audits(self):
        from loyalty.models import CampaignRule, LoyaltyTier
        url = reverse('superadmin:loyalty-config')
        self.client.post(url, {
            'action': 'save_config', 'property_id': str(self.prop.pk),
            'first_booking_pts': '250', 'pts_per_night': '120',
            'monthly_repeat_multiplier': '2.0',
        })
        log = self.last_audit('LOYALTY_CONFIG_UPDATED')
        self.assertIsNotNone(log)
        self.assertIn('250', log.detail)
        self.assertIn('120', log.detail)

        self.client.post(url, {'action': 'save_tier', 'name': 'Gold', 'min_pts': '500',
                               'discount_pct': '5', 'sort_order': '1'})
        self.assertIsNotNone(self.last_audit('LOYALTY_TIER_SAVED'))
        tier = LoyaltyTier.objects.get(name='Gold')
        self.client.post(url, {'action': 'delete_tier', 'tier_id': str(tier.pk)})
        self.assertIsNotNone(self.last_audit('LOYALTY_TIER_DELETED'))

        self.client.post(url, {'action': 'save_campaign', 'name': 'Diwali',
                               'start_date': '2026-11-01', 'end_date': '2026-11-10',
                               'multiplier': '2'})
        self.assertIsNotNone(self.last_audit('LOYALTY_CAMPAIGN_SAVED'))
        camp = CampaignRule.objects.get(name='Diwali')
        self.client.post(url, {'action': 'delete_campaign', 'campaign_id': str(camp.pk)})
        self.assertIsNotNone(self.last_audit('LOYALTY_CAMPAIGN_DELETED'))

    def test_tax_config_audit_has_old_and_new(self):
        res = self.client.post(reverse('superadmin:tax-config'), {
            'property_id': str(self.prop.pk), 'threshold': '9000',
            'low_rate_pct': '5', 'high_rate_pct': '18',
        })
        self.assertEqual(res.status_code, 302)
        res = self.client.post(reverse('superadmin:tax-config'), {
            'property_id': str(self.prop.pk), 'threshold': '8000',
            'low_rate_pct': '6', 'high_rate_pct': '20',
        })
        log = self.last_audit('TAX_CONFIG_UPDATED')
        self.assertIn('9000', log.detail)
        self.assertIn('8000', log.detail)
        self.assertIn('→', log.detail)

    def test_room_price_change_audit_has_old_and_new(self):
        with mock.patch(RECORD_ARI):
            res = self.post_json(reverse('superadmin:room-update', args=[self.room.pk]),
                                 {'action': 'update_details', 'price_per_night': '1500'})
        self.assertEqual(res.status_code, 200)
        log = self.last_audit('ROOM_UPDATED')
        self.assertIn('1000', log.detail)
        self.assertIn('1500', log.detail)


# ── H2 / H7 / M3 bad input ────────────────────────────────────────────────────

class BadInputTest(HardeningBase):
    def assert_400(self, res):
        self.assertEqual(res.status_code, 400, getattr(res, 'content', b'')[:300])

    # GET filters
    def test_bookings_list_bad_filters_do_not_500(self):
        url = reverse('superadmin:bookings')
        for params in ({'property': 'abc'}, {'from': 'notadate'}, {'to': '2026-13-45'},
                       {'status': 'bogus'}, {'property': 'abc', 'from': 'x', 'status': ';--'}):
            res = self.client.get(url, params)
            self.assertEqual(res.status_code, 200, params)

    def test_bookings_list_valid_status_still_filters(self):
        today = timezone.localdate()
        self.booking(today, today + timedelta(days=1), 'cancelled')
        res = self.client.get(reverse('superadmin:bookings'), {'status': 'confirmed'})
        self.assertEqual(len(res.context['bookings']), 0)

    def test_rooms_list_bad_property_does_not_500(self):
        res = self.client.get(reverse('superadmin:rooms'), {'property': 'abc'})
        self.assertEqual(res.status_code, 200)

    # room create (H2 + H7)
    def _room_post(self, **over):
        data = {'property_id': str(self.prop.pk), 'name': 'New', 'room_type': 'double',
                'price_per_night': '1800', 'capacity': '2', 'rating': '4.5'}
        data.update(over)
        return self.client.post(reverse('superadmin:room-create'), data)

    def test_room_create_rejects_bad_values(self):
        for over in ({'price_per_night': 'abc'}, {'price_per_night': 'NaN'},
                     {'price_per_night': '-5'}, {'price_per_night': '0'},
                     {'price_per_night': '999999999999'},
                     {'capacity': 'abc'}, {'capacity': '0'}, {'capacity': '21'},
                     {'rating': 'abc'}, {'rating': '9'}, {'rating': '-1'},
                     {'room_type': 'suite'}, {'property_id': 'not-a-uuid'}):
            with mock.patch(RECORD_ARI):
                self.assert_400(self._room_post(**over))
        self.assertFalse(Room.objects.filter(name='New').exists())

    def test_room_create_valid_pushes_availability(self):
        with mock.patch(RECORD_ARI) as ari:
            res = self._room_post()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(Room.objects.filter(name='New').exists())
        ari.assert_called_once()
        self.assertEqual(ari.call_args.args[0], 'double')
        self.assertEqual(ari.call_args.args[1], self.prop.pk)
        self.assertIn('availability', ari.call_args.kwargs['change_types'])

    # room update
    def test_room_update_malformed_json(self):
        res = self.client.post(reverse('superadmin:room-update', args=[self.room.pk]),
                               data='{not json', content_type='application/json')
        self.assert_400(res)

    def test_room_update_details_bad_values(self):
        url = reverse('superadmin:room-update', args=[self.room.pk])
        for payload in ({'rating': 'abc'}, {'capacity': 'abc'}, {'price_per_night': 'abc'},
                        {'price_per_night': '-10'}, {'capacity': 0}, {'capacity': 99},
                        {'rating': 7}, {'room_type': 'penthouse'},
                        {'property_id': 'zzz'}, {'name': ['x']}):
            payload['action'] = 'update_details'
            with mock.patch(RECORD_ARI):
                self.assert_400(self.post_json(url, payload))
        self.room.refresh_from_db()
        self.assertEqual(self.room.price_per_night, Decimal('1000.00'))

    def test_room_update_non_object_json(self):
        res = self.client.post(reverse('superadmin:room-update', args=[self.room.pk]),
                               data='[1,2]', content_type='application/json')
        self.assert_400(res)

    def test_toggle_active_pushes_availability(self):
        with mock.patch(RECORD_ARI) as ari:
            res = self.post_json(reverse('superadmin:room-update', args=[self.room.pk]),
                                 {'action': 'toggle_active'})
        self.assertEqual(res.status_code, 200)
        ari.assert_called_once()
        self.assertEqual(ari.call_args.args[0], 'single')
        self.assertEqual(ari.call_args.kwargs['change_types'], ('availability',))

    def test_type_change_pushes_old_and_new(self):
        other = Property.objects.create(name='Other', city='Bengaluru', address='x', is_active=True)
        with mock.patch(RECORD_ARI) as ari:
            res = self.post_json(reverse('superadmin:room-update', args=[self.room.pk]), {
                'action': 'update_details', 'room_type': 'deluxe', 'property_id': str(other.pk)})
        self.assertEqual(res.status_code, 200, res.content)
        pairs = {(c.args[0], c.args[1]) for c in ari.call_args_list}
        self.assertEqual(pairs, {('single', self.prop.pk), ('deluxe', other.pk)})
        for c in ari.call_args_list:
            self.assertEqual(set(c.kwargs['change_types']), {'availability', 'rates'})

    # employees / properties / events / causes / activities
    def test_employee_update_malformed_json(self):
        emp = _user('e1@test.com', 'employee')
        res = self.client.post(reverse('superadmin:employee-update', args=[emp.pk]),
                               data='{', content_type='application/json')
        self.assert_400(res)

    def test_employee_update_bad_property_ids(self):
        emp = _user('e2@test.com', 'employee')
        res = self.post_json(reverse('superadmin:employee-update', args=[emp.pk]),
                             {'action': 'update_properties', 'property_ids': ['nope']})
        self.assert_400(res)

    def test_property_update_malformed_json(self):
        res = self.client.post(reverse('superadmin:property-update', args=[self.prop.pk]),
                               data='nope', content_type='application/json')
        self.assert_400(res)

    def test_event_update_malformed_json_and_sort_order(self):
        from core.models import Attraction
        ev = Attraction.objects.create(name='Ev', city='Pondicherry', category='EVENT')
        url = reverse('superadmin:event-update', args=[ev.pk])
        self.assert_400(self.client.post(url, data='{', content_type='application/json'))
        self.assert_400(self.post_json(url, {'action': 'update_details', 'sort_order': 'abc'}))

    def test_cause_update_malformed_json_and_numbers(self):
        from core.models import Cause
        c = Cause.objects.create(title='C', location='L', description='d')
        url = reverse('superadmin:cause-update', args=[c.pk])
        self.assert_400(self.client.post(url, data='{', content_type='application/json'))
        self.assert_400(self.post_json(url, {'action': 'update_details', 'target_amount': 'abc'}))
        self.assert_400(self.post_json(url, {'action': 'update_details', 'sort_order': 'abc'}))
        self.assert_400(self.client.post(
            url, {'action': 'update_details', 'raised_amount': 'abc'}))

    def test_cause_create_bad_amount(self):
        res = self.client.post(reverse('superadmin:cause-create'), {
            'title': 'T', 'location': 'L', 'target_amount': 'abc'})
        self.assert_400(res)

    def test_activity_update_malformed_json_and_sort_order(self):
        from core.models import Activity
        a = Activity.objects.create(title='A', category='Yoga')
        url = reverse('superadmin:activity-update', args=[a.pk])
        self.assert_400(self.client.post(url, data='{', content_type='application/json'))
        self.assert_400(self.post_json(url, {'action': 'update_details', 'sort_order': 'abc'}))

    def test_event_image_upload_bad_sort_order(self):
        from core.models import Attraction
        ev = Attraction.objects.create(name='Ev2', city='Pondicherry', category='EVENT')
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            res = self.client.post(reverse('superadmin:event-image-upload', args=[ev.pk]),
                                   {'image': _png_upload(), 'sort_order': 'abc'})
        self.assert_400(res)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_banner_create_bad_sort_order_redirects(self):
        from core.models import SiteBanner
        res = self.client.post(reverse('superadmin:banner-create'), {
            'title': 'B', 'sort_order': 'abc', 'image': _png_upload()})
        self.assertEqual(res.status_code, 302)
        self.assertFalse(SiteBanner.objects.filter(title='B').exists())

    # tax config (M3)
    def _tax(self, **over):
        data = {'property_id': str(self.prop.pk), 'threshold': '7500',
                'low_rate_pct': '12', 'high_rate_pct': '18'}
        data.update(over)
        return self.client.post(reverse('superadmin:tax-config'), data)

    def test_tax_config_bad_numbers_redirect_and_not_saved(self):
        for over in ({'threshold': 'abc'}, {'low_rate_pct': 'x'}, {'high_rate_pct': ''},
                     {'threshold': '-1'}, {'low_rate_pct': '-2'}, {'high_rate_pct': '500'},
                     {'high_rate_pct': '28.01'}, {'low_rate_pct': '20', 'high_rate_pct': '10'},
                     {'threshold': 'NaN'}, {'threshold': '999999999999'},
                     {'property_id': 'not-a-uuid'}):
            res = self._tax(**over)
            self.assertEqual(res.status_code, 302, over)
        self.assertFalse(PropertyTaxConfig.objects.filter(property=self.prop).exists())
        self.assertFalse(AuditLog.objects.filter(action='TAX_CONFIG_UPDATED').exists())

    def test_tax_config_boundaries_accepted(self):
        res = self._tax(threshold='0', low_rate_pct='0', high_rate_pct='28')
        self.assertEqual(res.status_code, 302)
        cfg = PropertyTaxConfig.objects.get(property=self.prop)
        self.assertEqual(cfg.high_rate_pct, Decimal('28'))
        self.assertEqual(cfg.threshold, Decimal('0'))

    # loyalty config
    def test_loyalty_config_bad_input_redirects_and_saves_nothing(self):
        from loyalty.models import CampaignRule, LoyaltyConfig, LoyaltyTier
        url = reverse('superadmin:loyalty-config')
        bad = [
            {'action': 'save_config', 'property_id': str(self.prop.pk), 'first_booking_pts': 'abc'},
            {'action': 'save_config', 'property_id': str(self.prop.pk),
             'monthly_repeat_multiplier': 'x'},
            {'action': 'save_config', 'property_id': 'zzz'},
            {'action': 'save_tier', 'name': 'T', 'min_pts': 'abc'},
            {'action': 'save_tier', 'name': 'T', 'discount_pct': 'abc'},
            {'action': 'save_tier', 'name': 'T', 'sort_order': 'abc'},
            {'action': 'save_tier', 'name': ''},
            {'action': 'delete_tier', 'tier_id': 'abc'},
            {'action': 'save_campaign', 'name': 'C'},
            {'action': 'save_campaign', 'name': 'C', 'start_date': 'x', 'end_date': 'y'},
            {'action': 'save_campaign', 'name': 'C', 'start_date': '2026-05-02',
             'end_date': '2026-05-01'},
            {'action': 'save_campaign', 'name': 'C', 'start_date': '2026-05-01',
             'end_date': '2026-05-02', 'multiplier': 'abc'},
            {'action': 'delete_campaign', 'campaign_id': 'abc'},
            {'action': 'save_redemption_rule', 'name': 'R', 'points_cost': 'abc'},
            {'action': 'save_redemption_rule', 'name': 'R', 'discount_value': 'abc'},
            {'action': 'save_redemption_rule', 'name': 'R', 'validity_days': 'abc'},
        ]
        for data in bad:
            res = self.client.post(url, data)
            self.assertEqual(res.status_code, 302, data)
        self.assertEqual(LoyaltyTier.objects.count(), 0)
        self.assertEqual(CampaignRule.objects.count(), 0)
        self.assertEqual(LoyaltyConfig.objects.count(), 0)


# ── H5 cancel ─────────────────────────────────────────────────────────────────

class BookingCancelTest(HardeningBase):
    def test_cancel_confirmed_pushes_availability(self):
        today = timezone.localdate()
        ci, co = today + timedelta(days=5), today + timedelta(days=7)
        b = self.booking(ci, co)
        with mock.patch(RECORD_ARI) as ari:
            res = self.client.post(reverse('superadmin:booking-cancel', args=[b.pk]))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'cancelled')
        ari.assert_called_once_with(
            'single', self.prop.pk, ci, co, change_types=('availability',))

    def test_cancel_notes_refund_owed_in_audit(self):
        today = timezone.localdate()
        b = self.booking(today + timedelta(days=5), today + timedelta(days=7))
        Payment.objects.create(booking=b, amount=Decimal('1800.00'), status='captured',
                               payment_method=Payment.METHOD_RAZORPAY)
        Payment.objects.create(booking=b, amount=Decimal('999.00'), status='failed',
                               payment_method=Payment.METHOD_RAZORPAY)
        with mock.patch(RECORD_ARI):
            res = self.client.post(reverse('superadmin:booking-cancel', args=[b.pk]))
        self.assertEqual(res.status_code, 200)
        log = self.last_audit('BOOKING_CANCELLED')
        self.assertIn('refund owed', log.detail)
        self.assertIn('1800', log.detail)
        self.assertNotIn('2799', log.detail)

    def test_cancel_without_payment_has_no_refund_note(self):
        today = timezone.localdate()
        b = self.booking(today + timedelta(days=5), today + timedelta(days=7))
        with mock.patch(RECORD_ARI):
            self.client.post(reverse('superadmin:booking-cancel', args=[b.pk]))
        self.assertNotIn('refund', self.last_audit('BOOKING_CANCELLED').detail)

    def test_cancel_confirmed_keeps_redeemed_coupon(self):
        from loyalty.models import Coupon
        today = timezone.localdate()
        coupon = Coupon.objects.create(
            code='KEEP1', user=self.guest, discount_value=Decimal('100'),
            valid_until=timezone.now() + timedelta(days=5), status='redeemed')
        b = self.booking(today + timedelta(days=5), today + timedelta(days=7))
        b.coupon = coupon
        b.save(update_fields=['coupon'])
        with mock.patch(RECORD_ARI):
            self.client.post(reverse('superadmin:booking-cancel', args=[b.pk]))
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, 'redeemed')

    def test_cancel_pending_releases_applied_coupon(self):
        from loyalty.models import Coupon
        today = timezone.localdate()
        coupon = Coupon.objects.create(
            code='HOLD1', user=self.guest, discount_value=Decimal('100'),
            valid_until=timezone.now() + timedelta(days=5), status='applied')
        b = self.booking(today + timedelta(days=5), today + timedelta(days=7), 'pending')
        b.coupon = coupon
        b.save(update_fields=['coupon'])
        with mock.patch(RECORD_ARI):
            self.client.post(reverse('superadmin:booking-cancel', args=[b.pk]))
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, 'active')


# ── M6 employee_admin management ──────────────────────────────────────────────

class EmployeeAdminRoleTest(HardeningBase):
    def test_employee_admin_listed(self):
        _user('ea-list@test.com', 'employee_admin')
        res = self.client.get(reverse('superadmin:employees'))
        self.assertContains(res, 'ea-list@test.com')

    def test_employee_admin_can_be_locked_and_deleted(self):
        ea = _user('ea-lock@test.com', 'employee_admin')
        url = reverse('superadmin:employee-update', args=[ea.pk])
        res = self.post_json(url, {'action': 'lock'})
        self.assertEqual(res.status_code, 200)
        ea.refresh_from_db()
        self.assertFalse(ea.is_active)
        res = self.client.post(reverse('superadmin:employee-delete', args=[ea.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(pk=ea.pk).exists())

    def test_guest_cannot_be_managed(self):
        res = self.post_json(reverse('superadmin:employee-update', args=[self.guest.pk]),
                             {'action': 'lock'})
        self.assertEqual(res.status_code, 403)
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.is_active)

    def test_user_without_profile_rejected(self):
        ghost = _user('ghost@test.com', role=None)
        res = self.post_json(reverse('superadmin:employee-update', args=[ghost.pk]),
                             {'action': 'lock'})
        self.assertEqual(res.status_code, 403)
        ghost.refresh_from_db()
        self.assertTrue(ghost.is_active)


# ── Low ───────────────────────────────────────────────────────────────────────

class LowPriorityTest(HardeningBase):
    def test_cause_toggle_active_works_via_dispatcher(self):
        from core.models import Cause
        c = Cause.objects.create(title='C', location='L', description='d')
        res = self.post_json(reverse('superadmin:cause-update', args=[c.pk]),
                             {'action': 'toggle_active'})
        self.assertEqual(res.status_code, 200)
        c.refresh_from_db()
        self.assertFalse(c.is_active)

    def test_guests_list_booking_counts(self):
        today = timezone.localdate()
        self.booking(today, today + timedelta(days=1), 'confirmed')
        self.booking(today, today + timedelta(days=1), 'completed')
        self.booking(today, today + timedelta(days=1), 'cancelled')
        res = self.client.get(reverse('superadmin:guests'))
        self.assertEqual(res.status_code, 200)
        row = next(g for g in res.context['guests'] if g['user'].pk == self.guest.pk)
        self.assertEqual(row['booking_count'], 2)
        self.assertIsNotNone(row['profile'])

    def test_guests_list_query_count_is_flat(self):
        today = timezone.localdate()
        for i in range(5):
            g = _user(f'g{i}@test.com', 'guest')
            Booking.objects.create(user=g, room=self.room, check_in=today,
                                   check_out=today + timedelta(days=1), status='confirmed',
                                   total_price=Decimal('1'), guests=1)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('superadmin:guests'))
        booking_queries = [q for q in ctx.captured_queries if 'rooms_booking' in q['sql']
                           and 'COUNT' in q['sql'].upper() and 'GROUP BY' not in q['sql'].upper()]
        self.assertLessEqual(len(booking_queries), 2)
