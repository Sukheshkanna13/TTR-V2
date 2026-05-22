from urllib.parse import urlparse


CENTRAL_LOGIN_URL = "/accounts/login/page/"
CHANGE_PASSWORD_URL = "/accounts/change-password/"
HOME_URL = "/"
EMPLOYEE_ADMIN_DASHBOARD_URL = "/admin-portal/dashboard/"
SUPER_ADMIN_DASHBOARD_URL = "/super-admin/dashboard/"

ROLE_GUEST = "guest"
ROLE_EMPLOYEE = "employee"
ROLE_EMPLOYEE_ADMIN = "employee_admin"
ROLE_SUPER_ADMIN = "super_admin"

EMPLOYEE_ADMIN_ROLES = {ROLE_EMPLOYEE, ROLE_EMPLOYEE_ADMIN}
SUPER_ADMIN_ROLES = {ROLE_SUPER_ADMIN}


def get_user_profile(user):
    if not getattr(user, "is_authenticated", False):
        return None

    is_su = getattr(user, "is_superuser", False)
    try:
        profile = user.userprofile
        if is_su and profile.role != ROLE_SUPER_ADMIN:
            profile.role = ROLE_SUPER_ADMIN
            profile.save(update_fields=["role"])
        return profile
    except Exception:
        from accounts.models import UserProfile

        default_role = ROLE_SUPER_ADMIN if is_su else ROLE_GUEST
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": default_role})
        return profile


def get_user_role(user):
    if getattr(user, "is_superuser", False):
        return ROLE_SUPER_ADMIN
    profile = get_user_profile(user)
    return getattr(profile, "role", ROLE_GUEST) or ROLE_GUEST


def must_change_password(user):
    profile = get_user_profile(user)
    return bool(getattr(profile, "must_change_password", False))


def is_safe_local_path(path):
    if not path:
        return False

    parsed = urlparse(path)
    return parsed.scheme == "" and parsed.netloc == "" and path.startswith("/")


def is_role_allowed_for_path(role, path):
    if not is_safe_local_path(path):
        return False

    if path.startswith("/super-admin/"):
        return role in SUPER_ADMIN_ROLES

    if path.startswith("/admin-portal/"):
        return role in EMPLOYEE_ADMIN_ROLES

    return True


def get_default_redirect_for_role(role):
    if role == ROLE_SUPER_ADMIN:
        return SUPER_ADMIN_DASHBOARD_URL
    if role in EMPLOYEE_ADMIN_ROLES:
        return EMPLOYEE_ADMIN_DASHBOARD_URL
    return HOME_URL


def get_post_login_redirect(user, next_url=None):
    role = get_user_role(user)

    # Only guest accounts can be forced to change password.
    # Admin roles (employee_admin, super_admin) go straight to their dashboard —
    # only the super admin can reset employee passwords.
    if role == ROLE_GUEST and must_change_password(user):
        return CHANGE_PASSWORD_URL

    if next_url and is_role_allowed_for_path(role, next_url):
        return next_url

    return get_default_redirect_for_role(role)


def get_login_url_with_next(path):
    if is_safe_local_path(path):
        return f"{CENTRAL_LOGIN_URL}?next={path}"
    return CENTRAL_LOGIN_URL
