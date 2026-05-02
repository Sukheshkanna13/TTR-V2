"""
URL configuration for the rooms app (search only).

Routes:
    Page Views:
        /rooms/search/page/         — Room search page
        /rooms/room/page/           — Room detail page
    
    API Endpoints:
        GET /rooms/search/          — Search available rooms
        GET /rooms/<room_id>/       — Get room details
"""

from django.urls import path

from . import views

app_name = "rooms"

urlpatterns = [
    # Page views
    path("search/page/", views.search_page, name="search-page"),
    path("room/page/", views.room_detail_page, name="room-detail-page"),

    # API endpoints
    path("search/", views.SearchRoomsView.as_view(), name="search"),
    path("<uuid:room_id>/", views.RoomDetailView.as_view(), name="detail"),
]
