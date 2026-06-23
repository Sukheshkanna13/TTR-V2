"""
Core views for the hotel booking platform.
Handles landing page and general page views.
"""

from django.shortcuts import render


def home_page(request):
    """Render the landing page — search select is DB-driven; showcase content
    (featured cards, moments, journeys, tiers) mirrors the approved design.
    Booking links route into the Django flow (search/property), not external OTAs."""
    from rooms.models import Property
    cities = list(
        Property.objects.filter(is_active=True)
        .values_list('city', flat=True)
        .distinct()
        .order_by('city')
    )

    import datetime
    from django.utils import timezone
    today = timezone.localdate()
    ci, co = today + datetime.timedelta(days=1), today + datetime.timedelta(days=4)
    hero = {
        'city': cities[0] if cities else 'Pondicherry',
        'check_in_iso': ci.isoformat(), 'check_out_iso': co.isoformat(),
        'check_in_label': ci.strftime('%a, %b ') + str(ci.day),
        'check_out_label': co.strftime('%a, %b ') + str(co.day),
        'guests': 2,
    }

    def imgs(folder, nums):
        return [f"images/{folder}/{n}.jpeg" for n in nums]

    featured = [
        {'name': 'White Town 1BHK — 1st Floor', 'area': 'White Town · 100m from beach',
         'area_short': 'White Town', 'rating': '4.93', 'images': imgs('1F-1BHK', [1, 2, 3, 4, 5])},
        {'name': 'White Town 1BHK — 2nd Floor', 'area': 'White Town · 100m from beach',
         'area_short': 'White Town', 'rating': '4.86', 'images': imgs('2F-1BHK', [1, 2, 3, 4, 5])},
        {'name': 'Nature Retreat', 'area': 'Near Auroville · 1-acre garden & pool',
         'area_short': 'Near Auroville', 'rating': '4.90', 'images': imgs('Auroville', [1, 2, 3, 4, 5])},
    ]
    moments = [
        {'img': 'images/pottery.png', 'cap': 'Pottery, Near Auroville'},
        {'img': 'images/temple-courtyard.png', 'cap': 'Sandalwood courtyards'},
        {'img': 'images/sea-evening.png', 'cap': 'Promenade, dusk'},
        {'img': 'images/street-food.png', 'cap': 'White Town evenings'},
        {'img': 'images/morning-yoga.png', 'cap': 'Yoga Near Auroville'},
        {'img': 'images/banyan-tree.png', 'cap': 'Nature walks'},
    ]
    journeys = [
        {'img': 'images/nature.png', 'cat': 'Retreat', 'title': 'Mangroove', 'loc': 'Pondicherry'},
        {'img': 'images/coastal.png', 'cat': 'Heritage', 'title': 'Coastline', 'loc': 'White Town'},
        {'img': 'images/temple.png', 'cat': 'Culture', 'title': 'Culture', 'loc': 'Near Auroville'},
    ]
    tiers = [
        {'tier': 'Bronze', 'range': '0 – 499 pts', 'perks': 'Base rate'},
        {'tier': 'Silver', 'range': '500 – 1999 pts', 'perks': '5% off'},
        {'tier': 'Gold', 'range': '2000+ pts', 'perks': '12% off'},
    ]
    return render(request, "pages/index.html", {
        'cities': cities, 'hero': hero, 'featured': featured, 'moments': moments,
        'journeys': journeys, 'tiers': tiers,
    })


def experiences_page(request):
    """Render the Guest Experience page."""
    return render(request, "pages/experiences.html")


def things_to_do_page(request):
    """Render the Things to do page."""
    return render(request, "pages/things_to_do.html")


def cause_page(request):
    """Render the Travel for a Cause page."""
    from .models import Cause
    from rooms.models import Booking
    from django.db.models import Sum

    causes = Cause.objects.filter(is_active=True).order_by('sort_order', '-created_at')
    
    # Calculate impact stats
    total_raised_decimal = causes.aggregate(total=Sum('raised_amount'))['total'] or 0
    total_raised_lakhs = round(float(total_raised_decimal) / 100000, 1)
    if total_raised_lakhs.is_integer():
        total_raised_str = f"{int(total_raised_lakhs)}L"
    else:
        total_raised_str = f"{total_raised_lakhs}L"

    # Dynamic count of completed/confirmed bookings + static offset for mock scalability
    booking_count = Booking.objects.filter(status__in=('confirmed', 'completed')).count()
    guests_participated = 800 + booking_count
    
    active_programs = causes.count()

    return render(request, "pages/cause.html", {
        'causes': causes,
        'total_raised': total_raised_str,
        'guests_participated': guests_participated,
        'active_programs': active_programs,
    })



def explore_page(request):
    """Render the Explore page with Attraction model data and category filter."""
    from .models import Attraction
    category = request.GET.get('category', '')
    qs = Attraction.objects.filter(is_visible=True).prefetch_related('photos')
    if category:
        qs = qs.filter(category=category)
    return render(request, "pages/explore.html", {
        'attractions': qs,
        'categories': Attraction.CATEGORY_CHOICES,
        'selected_category': category,
    })
