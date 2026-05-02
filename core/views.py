"""
Core views for the hotel booking platform.
Handles landing page and general page views.
"""

from django.shortcuts import render


def home_page(request):
    """Render the landing page template."""
    return render(request, "pages/index.html")
