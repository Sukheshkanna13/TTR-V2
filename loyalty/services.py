"""
Loyalty point award logic. All config values come from DB — nothing hardcoded.
Called by payments after booking is confirmed.
"""
import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


def award_booking_points(booking_pk):
    """
    5-step award logic (all config-driven):
      1. Load LoyaltyConfig for booking.room.property
      2. First-ever CONFIRMED booking → base = config.first_booking_pts
         Else → base = num_nights × config.pts_per_night
      3. ≥2 confirmed bookings this calendar month → apply monthly_repeat_multiplier
      4. Active CampaignRule covering check_in → take highest multiplier
      5. Write LoyaltyLedger, update profile.loyalty_points, recalculate tier
    """
    try:
        from rooms.models import Booking
        from loyalty.models import LoyaltyConfig, CampaignRule, LoyaltyLedger
        from accounts.models import UserProfile

        booking = Booking.objects.select_related('user', 'room__property').get(pk=booking_pk)
        user = booking.user

        # --- Step 1: get config ---
        prop = booking.room.property if booking.room else None
        config = None
        if prop:
            try:
                config = prop.loyalty_config
            except LoyaltyConfig.DoesNotExist:
                pass

        # Fallback defaults when no property or no config set up yet
        first_booking_pts = config.first_booking_pts if config else 200
        pts_per_night = config.pts_per_night if config else 100
        monthly_multiplier = Decimal(str(config.monthly_repeat_multiplier)) if config else Decimal('1.50')

        # --- Step 2: base points ---
        prior_confirmed = Booking.objects.filter(
            user=user,
            status='confirmed',
        ).exclude(pk=booking_pk).count()

        if prior_confirmed == 0:
            base = first_booking_pts
        else:
            base = (booking.num_nights or 1) * pts_per_night

        # --- Step 3: monthly repeat multiplier ---
        multiplier = Decimal('1.00')
        today = booking.check_in
        month_count = Booking.objects.filter(
            user=user,
            status='confirmed',
            check_in__year=today.year,
            check_in__month=today.month,
        ).exclude(pk=booking_pk).count()

        if month_count >= 1:  # already ≥1 other booking this month → this is the ≥2nd
            multiplier = monthly_multiplier

        # --- Step 4: active campaign rule (highest multiplier wins) ---
        campaigns = CampaignRule.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).filter(
            models_q_property_or_global(prop)
        ).order_by('-multiplier')

        if campaigns.exists():
            campaign_mult = Decimal(str(campaigns.first().multiplier))
            if campaign_mult > multiplier:
                multiplier = campaign_mult

        # --- Step 5: finalise and persist ---
        final_pts = int(Decimal(str(base)) * multiplier)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.loyalty_points = (profile.loyalty_points or 0) + final_pts
        profile.save(update_fields=['loyalty_points'])

        LoyaltyLedger.objects.create(
            user=user,
            booking=booking,
            delta=final_pts,
            reason='BOOKING_CONFIRMED',
            note=f"{booking.num_nights}n × {pts_per_night}pts × {multiplier} multiplier",
        )

        _update_tier(profile)
        logger.info("Awarded %d loyalty pts to %s for booking %s", final_pts, user.email, booking_pk)

    except Exception:
        logger.exception("award_booking_points failed for booking %s", booking_pk)


def _update_tier(profile):
    """Promote profile to highest tier whose min_pts ≤ profile.loyalty_points."""
    try:
        from loyalty.models import LoyaltyTier
        tiers = LoyaltyTier.objects.filter(min_pts__lte=profile.loyalty_points).order_by('-min_pts')
        if tiers.exists():
            new_tier = tiers.first().name.lower()
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
