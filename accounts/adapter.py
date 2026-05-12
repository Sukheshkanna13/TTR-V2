from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Merge Google login with existing account if emails match.
        """
        # If user is already logged in, do nothing
        if sociallogin.is_existing:
            return

        # Check if email is provided
        if 'email' not in sociallogin.account.extra_data:
            return

        email = sociallogin.account.extra_data['email'].lower()
        try:
            # Check if a user with this email already exists
            user = User.objects.get(email=email)
            
            # If the user exists but isn't linked to this social account, link it
            sociallogin.connect(request, user)
            
            # Since they verified via Google, we can consider their account active
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
                
        except User.DoesNotExist:
            # Normal flow will create a new user
            pass
