from rest_framework import permissions

class IsEmployee(permissions.BasePermission):
    """
    Allows access only to employee and super_admin roles.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'userprofile') and 
            request.user.userprofile.role in ['employee', 'super_admin']
        )

class IsSuperAdmin(permissions.BasePermission):
    """
    Allows access only to super_admin role.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'userprofile') and 
            request.user.userprofile.role == 'super_admin'
        )
