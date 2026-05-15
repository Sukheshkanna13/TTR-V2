"""
Core views for the hotel booking platform.
Handles landing page and general page views.
"""

from django.shortcuts import render


def home_page(request):
    """Render the landing page — passes DB-driven city list for the search select."""
    from rooms.models import Property
    cities = list(
        Property.objects.filter(is_active=True)
        .values_list('city', flat=True)
        .distinct()
        .order_by('city')
    )
    return render(request, "pages/index.html", {'cities': cities})


def experiences_page(request):
    """Render the Guest Experience page."""
    return render(request, "pages/experiences.html")


def things_to_do_page(request):
    """Render the Things to do page."""
    return render(request, "pages/things_to_do.html")


def cause_page(request):
    """Render the Travel for a Cause page."""
    return render(request, "pages/cause.html")


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
