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
    return render(request, "pages/cause.html")


def retreat_page(request):
    """Nature Retreat — showcase page advertising the Near Auroville property."""
    highlights = [
        {'icon': 'wifi', 'title': 'High-speed Wi-Fi', 'desc': 'Stay connected throughout the property'},
        {'icon': 'sun', 'title': 'One Acre Garden', 'desc': 'Lush greenery and peaceful open spaces'},
        {'icon': 'shield', 'title': 'Swimming Pool', 'desc': 'Refreshing pool for guests of all ages'},
        {'icon': 'bed', 'title': '12 Rooms', 'desc': 'Comfortable rooms with attached baths'},
        {'icon': 'lock', 'title': 'Free Parking', 'desc': 'Secure on-site parking available'},
        {'icon': 'gift', 'title': 'Near Matrimandir', 'desc': '5-7 minutes from the iconic Matrimandir'},
    ]
    experiences = [
        {'title': 'Experience Local Artisans',
         'desc': 'Discover the charm of local craftsmanship through simple demonstrations and hands-on workshops. Meet local artisans, explore handmade jewellery, weaving and jute crafts.',
         'img': 'images/Natures-retreat/1.jpeg'},
        {'title': 'Garden Fun for Kids',
         'desc': 'Let the little hands explore nature through simple gardening and outdoor activities. A fun and joyful way for children to play, learn and enjoy the beauty of nature.',
         'img': 'images/Natures-retreat/2.jpeg'},
        {'title': 'Poolside Evenings & Summer Fun',
         'desc': 'Relax, unwind and enjoy refreshing moments by the pool. During special weekends and group stays — cheerful poolside gatherings and summer vibes.',
         'img': 'images/Natures-retreat/3.jpeg'},
    ]
    gallery = [f"images/Auroville/{n}.jpeg" for n in range(1, 9)]
    return render(request, "pages/retreat.html", {
        'highlights': highlights, 'experiences': experiences, 'gallery': gallery,
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
