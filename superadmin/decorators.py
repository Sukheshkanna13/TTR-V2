from functools import wraps
from django.shortcuts import redirect

def require_super_admin(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/super-admin/login/')
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'super_admin':
            return redirect('/super-admin/login/')
        return view_func(request, *args, **kwargs)
    return wrapper
