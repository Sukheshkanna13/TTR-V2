"""
URL configuration for core pages.
"""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home_page, name="home"),
    path("experiences/", views.experiences_page, name="experiences"),
    path("things-to-do/", views.things_to_do_page, name="things-to-do"),
    path("cause/", views.cause_page, name="cause"),
]
