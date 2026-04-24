"""
Email-based authentication backend and CSRF-exempt session auth.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from rest_framework.authentication import SessionAuthentication

User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    SessionAuthentication subclass that skips CSRF checks.
    DRF's default SessionAuthentication enforces CSRF on all
    authenticated requests. This is correct for browser forms,
    but breaks API testing from terminal/Postman/frontend apps.
    """

    def enforce_csrf(self, request):
        return  # Skip CSRF check


class EmailBackend(ModelBackend):
    """
    Authenticates users using email + password instead of username + password.
    """

    def authenticate(self, request, email=None, password=None, **kwargs):
        """
        Attempt to authenticate a user by email and password.
        Returns the user if credentials are valid, None otherwise.
        """
        if email is None:
            email = kwargs.get("username")
        if email is None or password is None:
            return None

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Run the default password hasher to mitigate timing attacks
            User().set_password(password)
            return None

        if user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
