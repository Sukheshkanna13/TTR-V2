# Admin Panels Remediation Plan (counter-attack on ADMIN-PANELS-AUDIT-2026-10-18)

**Branch:** `fix/admin-panels-audit` (cut from `feat/channex-foundation`)
**Goal:** close every Critical/High finding and the Medium items that touch money or availability, with regression tests, in a form that is safe to deploy.

## Execution model
Four Sonnet 5.5 agents work in parallel on **disjoint files** (no merge conflicts), after a shared foundation the orchestrator lands first.

### Wave 0 — foundation (orchestrator, done)
- `core/admin_utils.py`: `audit()`, `BadInput`, `parse_json`, `to_decimal`, `to_int`, `to_date`, `clean_uuid`, `clean_date`.
- `superadmin/models.py`: every audit action code both panels need, plus migration `0006_auditlog_action_choices` (choices only, so there's no DB change).

### Wave 1 — parallel agents

| Agent | Owns files (exclusive) | Findings |
|---|---|---|
| **A: Templates/XSS** | `templates/superadmin/*.html`, `templates/employeeadmin/*.html` | C1 XSS (escape every `innerHTML` interpolation), C4 hide price fields for fin=C |
| **B: Employee Admin** | `employeeadmin/views.py`, `employeeadmin/tests_hardening.py` (new) | C2, C4 (server side), H1 (audit every mutation), H2, H6, H7, M4, Low items |
| **C: Super Admin** | `superadmin/views.py`, `superadmin/tests_hardening.py` (new) | C2, C3, H1, H2, H5, H6, H7, M1, M2, M3, M6, Low items |
| **D: Rooms domain** | `rooms/tasks.py`, `rooms/services.py`, `rooms/migrations/00xx_fix_needs_cleaning.py` (new), `rooms/tests_admin_audit.py` (new) | H3 walk-in validation, H4 `needs_cleaning` + data migration |

Rules for all agents:
- Edit only owned files; read anything.
- Use `core/admin_utils.py`, not new local helpers.
- Write tests first for each finding (red → green), then run the full suite: `./venv/bin/python manage.py test`.
- Don't commit, push, or touch git; the orchestrator integrates.
- Don't modify `core/tests/test_channex_outbox.py` or `core/tests_ota.py` (the user's uncommitted work).

### Wave 2 — integration (orchestrator)
1. Review each agent's diff against its findings list.
2. Full test suite + `manage.py check --deploy --settings=hotel_booking.settings.prod` + `makemigrations --check`.
3. Re-run the audit probe; expect zero 5xx and every probe case rejected.
4. Commit in 4 logical commits (security → money/availability → hardening/audit → rooms domain), push `fix/admin-panels-audit`, open a PR into `feat/channex-foundation`.

## Deployment plan (VPS + Render)
1. **Pre-deploy:** take a DB backup (`mysqldump`/`pg_dump`), and confirm the qcluster worker is healthy.
2. **Deploy order:** code → `migrate` (two migrations: `superadmin.0006` is choices-only; the `rooms` data migration rewrites `needs_cleaning` → `cleaning`, is idempotent, and its reverse is a no-op) → `collectstatic` → restart gunicorn **and** qcluster (the tasks code changed).
3. **Smoke after deploy:**
   - log in as super admin and as employee
   - load the dashboard, bookings, rooms, analytics and audit log
   - create and cancel a test walk-in on a test room
   - confirm the audit-log rows appear and the analytics revenue includes completed stays
4. **Watch for 24h:** gunicorn error log for 5xx on `/super-admin/` and `/admin-portal/`, and the `ARIChange` outbox growth after cancels/room edits.
5. **Rollback:** redeploy the previous tag. Both migrations are backward-compatible, so there's no schema rollback.

## Behaviour changes to tell staff about
- Fin-level **C** employees can no longer change room prices, set walk-in rate overrides, or create rooms with a price. Ask a fin A/B employee or the super admin.
- "Mark completed" works only once the stay's check-out date has arrived (and early checkout shortens the stay).
- Analytics revenue now includes completed stays, so numbers will jump up. That's the correction, not an anomaly.
- Walk-ins reject unknown payment methods and guest counts above room capacity.

## Out of scope (tracked separately)
- Refund execution on cancel (cancellation/refund architecture plan), image upload validation (M5), the room-status/availability product decision (M7), deleting shadowed templates and `* 2.py` duplicates (M8, a separate housekeeping PR).
