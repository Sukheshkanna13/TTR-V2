import time
from django.contrib.auth import logout
from django.shortcuts import redirect

from .role_routing import (
    CENTRAL_LOGIN_URL,
    ROLE_EMPLOYEE_ADMIN,
    ROLE_SUPER_ADMIN,
    get_login_url_with_next,
    get_user_role,
)

class AutoLogoutMiddleware:
    """
    Middleware to auto-logout staff/admin users after 30 minutes of inactivity.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
            if get_user_role(request.user) in [ROLE_EMPLOYEE_ADMIN, ROLE_SUPER_ADMIN]:
                current_time = time.time()
                last_activity = request.session.get('last_activity', current_time)
                
                # 30 minutes = 1800 seconds
                if (current_time - last_activity) > 1800:
                    logout(request)
                    return redirect(get_login_url_with_next(request.path))
                
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
                    '/accounts/logout/',
                    '/admin/logout/',
                ]

                if not any(request.path.startswith(p) for p in exempt_paths):
                    return redirect('/accounts/change-password/')

        response = self.get_response(request)
        return response


class RoleRoutingMiddleware:
    """
    Middleware to route users to the correct login/portal based on role.

    Rules:
    - Authenticated users on /accounts/login/page/ stay on central login only if they choose to.
    - /admin-portal/*: requires employee_admin role
    - /super-admin/*: requires super_admin role only
    - /admin/*: requires is_superuser (Django built-in admin)
    - Guests hitting any staff path → /accounts/folio/
    - Unauthenticated hitting staff paths → central login page
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        user = request.user
        role = None
        if user.is_authenticated:
            role = get_user_role(user)

        # Django admin → superuser only
        if path.startswith('/admin/') and not path.startswith('/admin-portal/'):
            if not user.is_authenticated:
                return redirect(get_login_url_with_next(path))
            if not user.is_superuser:
                return redirect('/super-admin/dashboard/' if role == ROLE_SUPER_ADMIN else '/')

        # Super admin portal → super_admin role only
        if path.startswith('/super-admin/'):
            if not user.is_authenticated:
                return redirect(get_login_url_with_next(path))
            if role != ROLE_SUPER_ADMIN:
                return redirect(CENTRAL_LOGIN_URL)

        # Employee portal → employee or employee_admin role
        if path.startswith('/admin-portal/'):
            if not user.is_authenticated:
                return redirect(get_login_url_with_next(path))
            if role not in (ROLE_EMPLOYEE, ROLE_EMPLOYEE_ADMIN, ROLE_SUPER_ADMIN):
                return redirect(CENTRAL_LOGIN_URL)

        response = self.get_response(request)
        return response
