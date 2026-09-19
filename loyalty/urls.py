from django.urls import path
from . import views

app_name = "loyalty"

urlpatterns = [
    path("", views.rewards_dashboard, name="rewards-dashboard"),
    path("api/my-coupons/", views.my_coupons_api, name="my-coupons-api"),
    path("api/redeem/", views.redeem_coupon_api, name="redeem-api"),
    path("api/apply-coupon/", views.apply_coupon_api, name="apply-coupon-api"),
    path("api/remove-coupon/", views.remove_coupon_api, name="remove-coupon-api"),
]
