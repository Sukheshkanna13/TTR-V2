"""Injects loyalty context into every template for authenticated guests."""
import logging

logger = logging.getLogger(__name__)


def loyalty_context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        from loyalty.models import LoyaltyTier
        profile = getattr(request.user, 'userprofile', None)
        if not profile:
            return {}

        points = profile.loyalty_points or 0
        current_tier_name = profile.loyalty_tier or 'bronze'

        # Current tier from DB
        current_tier = LoyaltyTier.objects.filter(
            min_pts__lte=points
        ).order_by('-min_pts').first()

        # Next tier from DB
        next_tier = LoyaltyTier.objects.filter(
            min_pts__gt=points
        ).order_by('min_pts').first()

        progress_pct = 0
        if next_tier and current_tier:
            span = next_tier.min_pts - current_tier.min_pts
            earned = points - current_tier.min_pts
            progress_pct = min(100, int((earned / span) * 100)) if span > 0 else 100
        elif not next_tier:
            progress_pct = 100  # top tier

        return {
            'loyalty_points': points,
            'loyalty_tier': current_tier,
            'loyalty_tier_next': next_tier,
            'loyalty_progress_pct': progress_pct,
        }
    except Exception:
        logger.exception("loyalty_context processor failed")
        return {}
