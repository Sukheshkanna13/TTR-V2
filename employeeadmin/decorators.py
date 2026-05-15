from functools import wraps
from django.shortcuts import redirect

def require_employee(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/admin-portal/login/')
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ('employee', 'super_admin'):
            return redirect('/admin-portal/login/')
        return view_func(request, *args, **kwargs)
    return wrapper
