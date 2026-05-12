import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

class AutoLogoutMiddleware:
    """
    Middleware to auto-logout staff/admin users after 30 minutes of inactivity.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
            if request.user.userprofile.role in ['employee', 'super_admin']:
                current_time = time.time()
                last_activity = request.session.get('last_activity', current_time)
                
                # 30 minutes = 1800 seconds
                if (current_time - last_activity) > 1800:
                    logout(request)
                    return redirect(reverse('admin:login') + '?next=' + request.path)
                
                request.session['last_activity'] = current_time

        response = self.get_response(request)
        return response


class ForcePasswordChangeMiddleware:
    """
    Middleware to force users with must_change_password=True to change their password.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
            if request.user.userprofile.must_change_password:
                # Need to avoid redirect loop if they are already on the change password page or logging out
                # Assuming the change password url name is 'change-password' or similar. 
                # We'll match the path for simplicity.
                exempt_paths = [
                    '/accounts/change-password/',
                    '/admin/logout/',
                    '/api/auth/logout/'
                ]
                
                if not any(request.path.startswith(p) for p in exempt_paths):
                    return redirect('/accounts/change-password/')

        response = self.get_response(request)
        return response
