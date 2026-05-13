"""
URL configuration for the accounts app.

Routes:
    Page Views:
        /accounts/login/page/       — User login page
        /accounts/register/page/    — User registration page
        /accounts/folio/            — Guest folio / dashboard (login required)
    
    API Endpoints:
        POST /accounts/register/    — Register new user
        POST /accounts/verify-otp/  — Verify OTP
        POST /accounts/resend-otp/  — Resend OTP
        POST /accounts/login/       — User login
        POST /accounts/logout/      — User logout
        GET  /accounts/me/          — Get current user
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Page views
    path("login/page/", views.login_page, name="login-page"),
    path("register/page/", views.register_page, name="register-page"),
    path("folio/", views.folio_page, name="folio"),

    # API endpoints
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="verify-otp"),
    path("set-password/", views.SetPasswordView.as_view(), name="set-password"),
    path("resend-otp/", views.ResendOTPView.as_view(), name="resend-otp"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.CurrentUserView.as_view(), name="me"),
]
