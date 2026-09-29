"""
Email-based authentication backend.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


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
