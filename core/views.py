"""
Core views for the hotel booking platform.
Handles landing page and general page views.
"""

from django.shortcuts import render


def home_page(request):
    """Render the landing page template."""
    return render(request, "pages/index.html")


def experiences_page(request):
    """Render the Guest Experience page."""
    return render(request, "pages/experiences.html")


def things_to_do_page(request):
    """Render the Things to do page."""
    return render(request, "pages/things_to_do.html")


def cause_page(request):
    """Render the Travel for a Cause page."""
    return render(request, "pages/cause.html")
