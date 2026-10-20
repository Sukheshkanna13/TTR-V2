"""
Shared helpers for the Super Admin and Employee Admin panels.

- ``audit``: write an AuditLog row from any admin view.
- ``BadInput`` + parsers: turn malformed client input into a 400 instead of a 500.
  Views wrap their body in ``try: ... except BadInput as e: return e.response()``.
"""
import datetime as dt
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse


class BadInput(Exception):
    """Raised by the parsers below; carries a user-facing message."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message

    def response(self, status=400):
        return JsonResponse({'error': self.message}, status=status)


def audit(request, action, target_user=None, detail=''):
    """Record an admin action. ``action`` must be a key in AuditLog.ACTION_CHOICES."""
    from superadmin.models import AuditLog
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        target_user=target_user,
        detail=detail,
        ip_address=request.META.get('REMOTE_ADDR'),
    )


def parse_json(request):
    """Decode a JSON object body or raise BadInput."""
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise BadInput('Malformed JSON body.')
    if not isinstance(data, dict):
        raise BadInput('JSON body must be an object.')
    return data


def to_decimal(value, field, *, min_value=None, max_value=None):
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise BadInput(f'Invalid number for {field}.')
    if not result.is_finite():
        raise BadInput(f'Invalid number for {field}.')
    if min_value is not None and result < Decimal(str(min_value)):
        raise BadInput(f'{field} must be at least {min_value}.')
    if max_value is not None and result > Decimal(str(max_value)):
        raise BadInput(f'{field} must be at most {max_value}.')
    return result


def to_int(value, field, *, min_value=None, max_value=None):
    try:
        result = int(str(value).strip())
    except (ValueError, TypeError):
        raise BadInput(f'Invalid whole number for {field}.')
    if min_value is not None and result < min_value:
        raise BadInput(f'{field} must be at least {min_value}.')
    if max_value is not None and result > max_value:
        raise BadInput(f'{field} must be at most {max_value}.')
    return result


def to_date(value, field):
    try:
        return dt.date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        raise BadInput(f'Invalid date for {field} (expected YYYY-MM-DD).')


def clean_uuid(value):
    """Return the UUID string if valid, else None (for optional GET filters)."""
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def clean_date(value):
    """Return a date if ``value`` is ISO-formatted, else None (for optional GET filters)."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None
