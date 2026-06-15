# Super Admin — Employee Management Rebuild

**Date:** 2026-06-15
**Branch:** `fix/superadmin-employee-management`
**Status:** Approved

## Problem

The Super Admin "Employee Management" section is non-functional:

- **Edit, lock/unlock, reset-password, fin-level, and property-assignment all silently
  fail.** Root cause: the routes in `superadmin/urls.py` declare `<int:user_id>`, but
  `User.id` is a `UUIDField`. The template correctly sends the UUID, so the URL never
  resolves and every action 404s. The guest-loyalty route has the same defect.
- **No way to revoke or delete an employee** — only lock/unlock exists.
- **Temp-password UX is clunky/insecure** — `employee_create` and `reset_password`
  surface the plaintext password via `alert()` and a green box that auto-hides; the
  create flow auto-reloads after 2.5s.
- **No tracking** — the table doesn't show when an account was created, last login,
  who created it, or password status.
- A dead shadow template at `superadmin/templates/superadmin/employees.html` (the
  `templates/` copy wins via `DIRS`) causes confusion.

## Decisions

- **Credential reveal:** show once with a Copy button, no auto-hide. No email dependency.
- **Revoke/Delete:** soft-revoke is the default; permanent hard-delete offered only for
  accounts that never logged in.
- **Tracking columns:** Created date, Last login, Created by, Password status.

## Design

### 1. Root-cause fix
`superadmin/urls.py`: change `<int:user_id>` → `<uuid:user_id>` on the three employee
routes (update, plus new delete) and the guest-loyalty route.

### 2. Model changes — `accounts.UserProfile`
Add fields (business logic lives in the model):

- `created_by` — `FK(User, on_delete=SET_NULL, null=True, blank=True, related_name='employees_created')`
- `revoked_at` — `DateTimeField(null=True, blank=True)`
- `revoked_by` — `FK(User, on_delete=SET_NULL, null=True, blank=True, related_name='employees_revoked')`

Methods:

- `revoke(by_user)` — sets `user.is_active=False`, clears `assigned_properties`, stamps
  `revoked_at=now()` + `revoked_by`. **Keeps** `role='employee'` so the record still lists.
- `reinstate()` — clears `revoked_at`/`revoked_by`, sets `user.is_active=True`.
- `can_hard_delete` (property) — `True` only when `user.last_login is None`.

One migration in `accounts`. Created date uses existing `User.date_joined`; last login uses
existing `User.last_login`.

### 3. Employee state model
| State | Condition | Actions |
|-------|-----------|---------|
| Active | `is_active`, no `revoked_at` | Lock · Reset PW · Revoke · edit fin/props |
| Locked | `!is_active`, no `revoked_at` | Unlock · Reset PW · Revoke |
| Revoked | `revoked_at` set, access stripped | Permanently delete (if eligible) · Reinstate |
| Deleted | row removed | — (only if `last_login is None`) |

### 4. Credential reveal
Backend unchanged (still returns `temp_password` once on create/reset). Frontend replaces
`alert()` + auto-hide with a reveal modal: shows the password, a Copy button, stays open
until dismissed; reload on close. Remove the 2.5s auto-reload.

### 5. Endpoints + audit
- `revoke` and `reinstate` actions added to `employee_update` → `EMPLOYEE_REVOKED` /
  `EMPLOYEE_UNLOCKED`.
- New route `employees/<uuid:user_id>/delete/` (POST, super-admin) — hard delete; returns
  400 "Account has activity — revoke instead" when `can_hard_delete` is False. Logs
  `EMPLOYEE_DELETED` **before** deletion (target_user is `SET_NULL`).
- Guard: a super admin cannot revoke or delete their own account.
- New `AuditLog.ACTION_CHOICES`: `EMPLOYEE_REVOKED`, `EMPLOYEE_DELETED`. One `superadmin`
  migration.

### 6. Tracking table
`employees_list` and the template gain: Created (`date_joined`), Last login, Created by
(`select_related`), PW status (`must_change_password`), and a Status badge
(Active / Locked / Revoked). `employee_create` records `created_by=request.user`.

### 7. Cleanup
Delete `superadmin/templates/superadmin/employees.html` (dead).

### 8. Tests (TDD)
- UUID routes resolve and each `employee_update` action succeeds with a real UUID pk.
- `revoke()` strips access + stamps; appears in list as Revoked.
- Hard-delete blocked when `last_login` set, allowed when `None`.
- Self-protection guard blocks self revoke/delete.
- `employees_list` returns enriched fields.

## Scalability
`revoke()` / `reinstate()` / `can_hard_delete` live on the model, keeping views thin and
reusable for future bulk actions or an API.
