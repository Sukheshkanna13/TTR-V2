"""
URL configuration for payment endpoints.

Routes:
    Page Views:
        /payments/checkout/page/    — Checkout page
    
    API Endpoints:
        POST /payments/create-order/ — Create Razorpay order
        POST /payments/verify/       — Verify payment
        POST /payments/webhook/      — Razorpay webhook
"""

from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    # Page views
    path("checkout/page/", views.checkout_page, name="checkout-page"),

    # API endpoints
    path("create-order/", views.CreateOrderView.as_view(), name="create-order"),
    path("verify/", views.VerifyPaymentView.as_view(), name="verify"),
    path("webhook/", views.WebhookView.as_view(), name="webhook"),
]
