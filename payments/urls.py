"""
URL configuration for payment endpoints.
"""

from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("create-order/", views.CreateOrderView.as_view(), name="create-order"),
    path("verify/", views.VerifyPaymentView.as_view(), name="verify"),
    path("webhook/", views.WebhookView.as_view(), name="webhook"),
]
