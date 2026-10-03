from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

from accounts.role_routing import CENTRAL_LOGIN_URL, ROLE_GUEST, get_user_role

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Merge Google login with existing account if emails match.
        """
        # If user is already logged in, do nothing
        if sociallogin.is_existing:
            return

        # Check if email is provided and verified by provider
        extra_data = sociallogin.account.extra_data
        if 'email' not in extra_data:
            return

        # AUTH-02: Only merge if the OAuth provider asserts the email is verified
        is_verified = extra_data.get('email_verified') or extra_data.get('verified_email')
        if not is_verified:
            return

        email = extra_data['email'].lower()
        try:
            # Check if a user with this email already exists
            user = User.objects.get(email=email)

            # A deactivated staff account is locked or revoked by a super admin.
            # A Google-verified email must never bypass that decision.
            if not user.is_active and get_user_role(user) != ROLE_GUEST:
                raise ImmediateHttpResponse(redirect(CENTRAL_LOGIN_URL))

            # If the user exists but isn't linked to this social account, link it
            sociallogin.connect(request, user)

            # An unverified guest who proves ownership of the email via Google is active
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

        except User.DoesNotExist:
            # Normal flow will create a new user
            pass
