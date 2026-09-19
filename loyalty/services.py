"""
Loyalty point award and coupon redemption logic.
All config values come from DB — nothing hardcoded.
"""
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Tuple, Optional, Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def award_booking_points(booking_pk):
    """
    5-step award logic (all config-driven, atomic, and concurrency-safe):
      1. Load LoyaltyConfig for booking.room.property
      2. First-ever CONFIRMED booking → base = config.first_booking_pts
         Else → base = num_nights × config.pts_per_night
      3. ≥2 confirmed bookings this calendar month → apply monthly_repeat_multiplier
      4. Active CampaignRule covering check_in → take highest multiplier
      5. Write LoyaltyLedger, update profile.loyalty_points, recalculate tier

    Called by rooms.tasks.award_loyalty_for_completed_stays 24h after checkout
    for bookings that are still CONFIRMED (not cancelled).
    """
    try:
        from rooms.models import Booking
        from loyalty.models import LoyaltyConfig, CampaignRule, LoyaltyLedger
        from accounts.models import UserProfile

        with transaction.atomic():
            booking = Booking.objects.select_for_update().select_related('user', 'room__property').get(pk=booking_pk)
            if booking.loyalty_awarded:
                return

            # Check if ledger row already exists to prevent duplicate awards
            if LoyaltyLedger.objects.filter(booking=booking, reason='BOOKING_CONFIRMED').exists():
                booking.loyalty_awarded = True
                booking.save(update_fields=['loyalty_awarded'])
                return

            user = booking.user

            # --- Step 1: get config ---
            prop = booking.room.property if booking.room is not None else None
            config = None
            if prop:
                try:
                    config = prop.loyalty_config
                except LoyaltyConfig.DoesNotExist:
                    pass

            # --- Step 2-4: compute points and multiplier ---
            base, multiplier, pts_per_night = _compute_pts_and_multiplier(booking, user, prop, config)

            # --- Step 5: finalise and persist ---
            final_pts = int(Decimal(str(base)) * multiplier)

            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
            profile.loyalty_points = (profile.loyalty_points or 0) + final_pts
            profile.save(update_fields=['loyalty_points'])

            LoyaltyLedger.objects.create(
                user=user,
                booking=booking,
                delta=final_pts,
                reason='BOOKING_CONFIRMED',
                note=f"{booking.num_nights}n × {pts_per_night}pts × {multiplier} multiplier",
            )

            booking.loyalty_awarded = True
            booking.save(update_fields=['loyalty_awarded'])

            _update_tier(profile)
            logger.info("Awarded %d loyalty pts to %s for booking %s", final_pts, user.email, booking_pk)

    except Exception:
        logger.exception("award_booking_points failed for booking %s", booking_pk)


def redeem_points_for_coupon(user, rule_id) -> Tuple[bool, Optional[Any], str]:
    """
    Converts loyalty points into a discount coupon according to a CouponRedemptionRule.
    Atomic with row-locking to prevent concurrent double-spend race conditions.
    """
    from accounts.models import UserProfile
    from loyalty.models import CouponRedemptionRule, Coupon, LoyaltyLedger

    if not user or not user.is_authenticated:
        return False, None, "Authentication required."

    with transaction.atomic():
        try:
            profile = UserProfile.objects.select_for_update().get(user=user)
        except UserProfile.DoesNotExist:
            return False, None, "User profile not found."

        try:
            rule = CouponRedemptionRule.objects.get(id=rule_id, is_active=True)
        except CouponRedemptionRule.DoesNotExist:
            return False, None, "Redemption rule not found or inactive."

        current_points = profile.loyalty_points or 0
        if current_points < rule.points_cost:
            return (
                False,
                None,
                f"Insufficient points. Required: {rule.points_cost}, Available: {current_points}.",
            )

        # Debit points
        profile.loyalty_points = current_points - rule.points_cost
        profile.save(update_fields=['loyalty_points'])

        # Create Ledger Audit entry
        LoyaltyLedger.objects.create(
            user=user,
            delta=-rule.points_cost,
            reason='COUPON_REDEMPTION',
            note=f"Redeemed for {rule.name} ({rule.discount_display})",
        )

        # Generate unique code
        code_str = f"TTR-{secrets.token_hex(4).upper()}"
        while Coupon.objects.filter(code=code_str).exists():
            code_str = f"TTR-{secrets.token_hex(4).upper()}"

        now = timezone.now()
        coupon = Coupon.objects.create(
            code=code_str,
            user=user,
            redemption_rule=rule,
            discount_type=rule.discount_type,
            discount_value=rule.discount_value,
            min_booking_amount=rule.min_booking_amount,
            max_discount_amount=rule.max_discount_amount,
            valid_from=now,
            valid_until=now + timedelta(days=rule.validity_days),
            status=Coupon.STATUS_ACTIVE,
        )

        _update_tier(profile)
        logger.info(
            "User %s redeemed %d pts for coupon %s",
            user.email,
            rule.points_cost,
            coupon.code,
        )
        return True, coupon, f"Successfully redeemed voucher {coupon.code}!"


def apply_coupon_to_booking(booking_id, coupon_code: str, user=None) -> Tuple[bool, str, Decimal, Decimal]:
    """
    Validates and applies a coupon to a pending booking.
    Calculates discount, recalculates GST on discounted amount, and reserves coupon.
    Returns (success, message, discount_amount, payable_amount).
    """
    from rooms.models import Booking
    from loyalty.models import Coupon

    if not coupon_code or not coupon_code.strip():
        return False, "Please enter a coupon code.", Decimal('0.00'), Decimal('0.00')

    cleaned_code = coupon_code.strip().upper()

    with transaction.atomic():
        try:
            booking = (
                Booking.objects.select_for_update()
                .select_related('room__property', 'coupon')
                .get(id=booking_id)
            )
        except Booking.DoesNotExist:
            return False, "Booking not found.", Decimal('0.00'), Decimal('0.00')

        if booking.status != "pending":
            return False, f"Cannot apply coupon to booking with status: {booking.status}.", Decimal('0.00'), booking.payable_amount

        if booking.expire_if_needed():
            return False, "Your booking hold has expired.", Decimal('0.00'), Decimal('0.00')

        # If booking already has this exact coupon applied, return current state
        if booking.coupon and booking.coupon.code.upper() == cleaned_code:
            return (
                True,
                f"Coupon '{cleaned_code}' is already applied.",
                booking.discount_amount,
                booking.payable_amount,
            )

        # If another coupon was previously applied to this booking, release it first
        if booking.coupon:
            old_coupon = booking.coupon
            if old_coupon.status == Coupon.STATUS_APPLIED:
                old_coupon.status = Coupon.STATUS_ACTIVE
                old_coupon.save(update_fields=['status'])
            booking.coupon = None
            booking.discount_amount = Decimal('0.00')

        # Find requested coupon
        try:
            coupon = Coupon.objects.select_for_update().get(code__iexact=cleaned_code)
        except Coupon.DoesNotExist:
            return False, "Invalid coupon code.", Decimal('0.00'), booking.payable_amount

        # Validate against booking and user
        is_valid, error_msg = coupon.validate_for_booking(booking, user=user)
        if not is_valid:
            return False, error_msg, Decimal('0.00'), booking.payable_amount

        # Calculate discount
        discount = coupon.calculate_discount(booking.total_price)
        if discount <= Decimal('0.00'):
            return False, "This coupon does not provide any discount for this booking.", Decimal('0.00'), booking.payable_amount

        # Transition coupon to applied
        coupon.status = Coupon.STATUS_APPLIED
        coupon.save(update_fields=['status'])

        booking.coupon = coupon
        booking.discount_amount = discount
        booking.save(update_fields=['coupon', 'discount_amount'])
        booking.compute_tax()

        return (
            True,
            f"Coupon '{coupon.code}' applied! You saved ₹{discount}.",
            discount,
            booking.payable_amount,
        )


def remove_coupon_from_booking(booking_id, user=None) -> Tuple[bool, str, Decimal]:
    """
    Removes applied coupon from a pending booking and returns the coupon to active status.
    Returns (success, message, new_payable_amount).
    """
    from rooms.models import Booking
    from loyalty.models import Coupon

    with transaction.atomic():
        try:
            booking = (
                Booking.objects.select_for_update()
                .select_related('coupon')
                .get(id=booking_id)
            )
        except Booking.DoesNotExist:
            return False, "Booking not found.", Decimal('0.00')

        if not booking.coupon:
            return False, "No coupon applied to this booking.", booking.payable_amount

        if user and booking.user_id != user.id:
            return False, "Unauthorized.", booking.payable_amount

        coupon = booking.coupon
        if coupon.status == Coupon.STATUS_APPLIED:
            coupon.status = Coupon.STATUS_ACTIVE
            coupon.save(update_fields=['status'])

        booking.coupon = None
        booking.discount_amount = Decimal('0.00')
        booking.save(update_fields=['coupon', 'discount_amount'])
        booking.compute_tax()

        return True, "Coupon removed successfully.", booking.payable_amount


def _compute_pts_and_multiplier(booking, user, prop, config):
    from decimal import Decimal
    from rooms.models import Booking
    from loyalty.models import CampaignRule

    first_booking_pts = config.first_booking_pts if config else 200
    pts_per_night = config.pts_per_night if config else 100
    monthly_multiplier = Decimal(str(config.monthly_repeat_multiplier)) if config else Decimal('1.50')

    prior_confirmed = Booking.objects.filter(
        user=user,
        status='confirmed',
    ).exclude(pk=booking.pk).count()

    if prior_confirmed == 0:
        base = first_booking_pts
    else:
        base = (booking.num_nights or 1) * pts_per_night

    multiplier = Decimal('1.00')
    today = booking.check_in
    month_count = Booking.objects.filter(
        user=user,
        status='confirmed',
        check_in__year=today.year,
        check_in__month=today.month,
    ).exclude(pk=booking.pk).count()

    if month_count >= 1:
        multiplier = monthly_multiplier

    campaigns = CampaignRule.objects.filter(
        is_active=True,
        start_date__lte=today,
        end_date__gte=today,
    ).filter(
        models_q_property_or_global(prop)
    ).order_by('-multiplier')

    active_campaign = campaigns.first()
    if active_campaign is not None:
        campaign_mult = Decimal(str(active_campaign.multiplier))
        if campaign_mult > multiplier:
            multiplier = campaign_mult

    return base, multiplier, pts_per_night


def _update_tier(profile):
    """Promote profile to highest tier whose min_pts ≤ profile.loyalty_points."""
    try:
        from loyalty.models import LoyaltyTier
        tiers = LoyaltyTier.objects.filter(min_pts__lte=profile.loyalty_points).order_by('-min_pts')
        top_tier = tiers.first()
        if top_tier is not None:
            new_tier = top_tier.name.lower()
            if profile.loyalty_tier != new_tier:
                profile.loyalty_tier = new_tier
                profile.save(update_fields=['loyalty_tier'])
    except Exception:
        logger.exception("_update_tier failed for user %s", profile.user_id)


def models_q_property_or_global(prop):
    """Q object: match campaigns for this specific property OR platform-wide (property=None)."""
    from django.db.models import Q
    if prop:
        return Q(property=prop) | Q(property__isnull=True)
    return Q(property__isnull=True)
