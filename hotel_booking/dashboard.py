"""
Admin dashboard callback for django-unfold.

Provides live stats on the admin homepage:
- Today's booking count
- Today's revenue
- Today's check-ins
"""

from datetime import date

from django.db.models import Count, Q, Sum


def dashboard_callback(request, context):
    """
    Called by django-unfold to inject dashboard data into the admin homepage.
    All values are pulled live from the database.
    """
    from rooms.models import Booking

    today = date.today()

    # Today's confirmed bookings (created today)
    todays_bookings = Booking.objects.filter(
        created_at__date=today,
        status="confirmed",
    ).count()

    # Today's revenue (sum of confirmed bookings created today)
    todays_revenue = Booking.objects.filter(
        created_at__date=today,
        status="confirmed",
    ).aggregate(total=Sum("total_price"))["total"] or 0

    # Today's check-ins (guests arriving today)
    todays_checkins = Booking.objects.filter(
        check_in=today,
        status="confirmed",
    ).count()

    # Total active bookings (pending + confirmed)
    active_bookings = Booking.objects.filter(
        status__in=["pending", "confirmed"],
    ).count()

    # Pending holds right now
    pending_holds = Booking.objects.filter(
        status="pending",
    ).count()

    context.update(
        {
            "dashboard_stats": [
                {
                    "label": "Today's Confirmed Bookings",
                    "value": todays_bookings,
                    "icon": "book_online",
                },
                {
                    "label": "Today's Revenue",
                    "value": f"Rs. {todays_revenue:,.2f}",
                    "icon": "payments",
                },
                {
                    "label": "Today's Check-ins",
                    "value": todays_checkins,
                    "icon": "login",
                },
                {
                    "label": "Active Bookings",
                    "value": active_bookings,
                    "icon": "event_available",
                },
                {
                    "label": "Pending Holds",
                    "value": pending_holds,
                    "icon": "hourglass_top",
                },
            ],
        }
    )

    return context
