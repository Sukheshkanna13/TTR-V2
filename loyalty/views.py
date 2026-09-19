import json
import logging
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import UserProfile
from loyalty.models import LoyaltyTier, CouponRedemptionRule, Coupon, LoyaltyLedger
from loyalty.services import (
    redeem_points_for_coupon,
    apply_coupon_to_booking,
    remove_coupon_from_booking,
)

logger = logging.getLogger(__name__)


@login_required(login_url="/accounts/login/page/")
def rewards_dashboard(request):
    """
    Renders guest loyalty and rewards portal.
    Shows points balance, current tier, progress bar, active coupons, and instant redeem cards.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    pts = profile.loyalty_points or 0
    now = timezone.now()

    # Tiers & progress
    tiers = list(LoyaltyTier.objects.order_by("min_pts"))
    current_tier_obj = None
    next_tier_obj = None

    if tiers:
        for t in reversed(tiers):
            if pts >= t.min_pts:
                current_tier_obj = t
                break
        if not current_tier_obj:
            current_tier_obj = tiers[0]

        # Find next tier
        for t in tiers:
            if t.min_pts > pts:
                next_tier_obj = t
                break

    progress_pct = 100
    pts_to_next = 0
    if next_tier_obj and current_tier_obj:
        range_pts = next_tier_obj.min_pts - current_tier_obj.min_pts
        if range_pts > 0:
            earned_in_tier = pts - current_tier_obj.min_pts
            progress_pct = min(100, max(0, int((earned_in_tier / range_pts) * 100)))
        pts_to_next = next_tier_obj.min_pts - pts

    # Active Redemption Rules (catalog to buy coupons)
    rules = CouponRedemptionRule.objects.filter(is_active=True).order_by("points_cost")

    # Active & applied vouchers owned by guest
    active_coupons = Coupon.objects.filter(
        user=request.user,
        status=Coupon.STATUS_ACTIVE,
        valid_until__gt=now,
    ).order_by("-created_at")

    applied_coupons = Coupon.objects.filter(
        user=request.user,
        status=Coupon.STATUS_APPLIED,
    ).order_by("-created_at")

    history_coupons = Coupon.objects.filter(
        user=request.user,
    ).exclude(status__in=[Coupon.STATUS_ACTIVE, Coupon.STATUS_APPLIED]).order_by("-created_at")[:10]

    # Ledger history
    ledger_entries = LoyaltyLedger.objects.filter(user=request.user).order_by("-created_at")[:20]

    return render(
        request,
        "loyalty/rewards.html",
        {
            "profile": profile,
            "points": pts,
            "current_tier": current_tier_obj,
            "next_tier": next_tier_obj,
            "progress_pct": progress_pct,
            "pts_to_next": pts_to_next,
            "tiers": tiers,
            "rules": rules,
            "active_coupons": active_coupons,
            "applied_coupons": applied_coupons,
            "history_coupons": history_coupons,
            "ledger_entries": ledger_entries,
        },
    )


@require_GET
def my_coupons_api(request):
    """
    Returns active, non-expired coupons owned by the logged-in guest.
    Used by checkout modal/dropdown.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required.", "coupons": []}, status=401)

    now = timezone.now()
    coupons = Coupon.objects.filter(
        user=request.user,
        status=Coupon.STATUS_ACTIVE,
        valid_until__gt=now,
    ).order_by("-created_at")

    data = [
        {
            "id": str(c.id),
            "code": c.code,
            "discount_type": c.discount_type,
            "discount_value": str(c.discount_value),
            "discount_display": c.discount_display,
            "min_booking_amount": str(c.min_booking_amount),
            "max_discount_amount": str(c.max_discount_amount) if c.max_discount_amount else None,
            "valid_until": c.valid_until.strftime("%d %b %Y"),
        }
        for c in coupons
    ]
    return JsonResponse({"coupons": data})


@require_POST
def redeem_coupon_api(request):
    """
    Redeems points for a voucher rule.
    Expects JSON: { "rule_id": "<uuid>" } or form data.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required."}, status=401)

    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        payload = {}

    rule_id = payload.get("rule_id")
    if not rule_id:
        return JsonResponse({"success": False, "error": "Rule ID is required."}, status=400)

    success, coupon, msg = redeem_points_for_coupon(request.user, rule_id)
    if not success:
        return JsonResponse({"success": False, "error": msg}, status=400)

    profile = getattr(request.user, "userprofile", None)
    pts_balance = profile.loyalty_points if profile else 0

    return JsonResponse(
        {
            "success": True,
            "message": msg,
            "coupon": {
                "id": str(coupon.id),
                "code": coupon.code,
                "discount_display": coupon.discount_display,
                "valid_until": coupon.valid_until.strftime("%d %b %Y"),
            },
            "points_balance": pts_balance,
        }
    )


@require_POST
def apply_coupon_api(request):
    """
    Applies a coupon code to a booking hold.
    Expects JSON: { "booking_id": "<uuid>", "coupon_code": "..." } or form data.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required."}, status=401)

    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        payload = {}

    booking_id = payload.get("booking_id")
    coupon_code = payload.get("coupon_code", "").strip()

    if not booking_id or not coupon_code:
        return JsonResponse(
            {"success": False, "error": "Booking ID and Coupon Code are required."},
            status=400,
        )

    success, msg, discount, payable = apply_coupon_to_booking(
        booking_id=booking_id,
        coupon_code=coupon_code,
        user=request.user,
    )

    if not success:
        return JsonResponse(
            {
                "success": False,
                "error": msg,
                "payable_amount": str(payable),
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "message": msg,
            "coupon_code": coupon_code.upper(),
            "discount_amount": str(discount),
            "payable_amount": str(payable),
        }
    )


@require_POST
def remove_coupon_api(request):
    """
    Removes applied coupon from a booking hold and restores the coupon.
    Expects JSON: { "booking_id": "<uuid>" } or form data.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required."}, status=401)

    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        payload = {}

    booking_id = payload.get("booking_id")
    if not booking_id:
        return JsonResponse({"success": False, "error": "Booking ID is required."}, status=400)

    success, msg, payable = remove_coupon_from_booking(booking_id=booking_id, user=request.user)
    if not success:
        return JsonResponse({"success": False, "error": msg}, status=400)

    return JsonResponse(
        {
            "success": True,
            "message": msg,
            "payable_amount": str(payable),
        }
    )
