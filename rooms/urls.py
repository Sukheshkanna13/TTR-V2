"""
URL configuration for the rooms app (search only).
"""

from django.urls import path

from . import views

app_name = "rooms"

urlpatterns = [
    path("search/", views.SearchRoomsView.as_view(), name="search"),
]
