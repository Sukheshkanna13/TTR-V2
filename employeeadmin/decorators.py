from functools import wraps
from django.shortcuts import redirect

from accounts.role_routing import (
    CENTRAL_LOGIN_URL, EMPLOYEE_ADMIN_ROLES, ROLE_SUPER_ADMIN, get_user_role,
)

def require_employee(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(CENTRAL_LOGIN_URL)
        role = get_user_role(request.user)
        if role not in EMPLOYEE_ADMIN_ROLES and role != ROLE_SUPER_ADMIN:
            return redirect(CENTRAL_LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper

