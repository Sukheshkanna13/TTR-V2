# Security audit — 2026-09-29

Daily-mode audit (8/10 confidence gate) of `bugfixes/render-deploy`, code-traced with no
live requests. Machine-readable copy: `.gstack/security-reports/2026-09-29-audit.json`
(gitignored). Not run: global-skill scan (needs permission to read outside the repo).
Dependency scan (`pip-audit -r requirements.txt`) done: the setuptools pin was raised from
`<70` to `>=78.1.1,<81`, clearing 4 of 6 advisories. The last, PYSEC-2026-3447, needs
setuptools 83, which drops `pkg_resources` and would break razorpay 1.4's client import. It
affects package building, not the running web app; revisit when razorpay drops `pkg_resources`.

| # | Sev | Finding | Status |
|---|-----|---------|--------|
| 1 | CRIT | Gmail app passwords in git history (`e497272`, `31eef19`) and in tracked `.env.example` | Placeholder fix committed. **Open:** rotate the passwords; history still contains them (rewrite needs an explicit go-ahead) |
| 2 | CRIT | `build.sh` created superadmin with default password `Admin@1234` | Fixed: env-only, skipped when unset |
| 3 | HIGH | Google login re-activated locked/revoked staff (`accounts/adapter.py`) | Fixed + tests |
| 4 | HIGH | Console email backend hard-coded in `prod.py` (OTPs in logs, no email on VPS) | Fixed: `EMAIL_BACKEND` env; Render default unchanged. VPS env template sets SMTP |
| 5 | MED | `CsrfExemptSessionAuthentication` was the DRF default, so session-authenticated API endpoints skipped CSRF | Fixed: standard `SessionAuthentication`; templates already sent `X-CSRFToken`. Anonymous endpoints and webhooks are unaffected; hold-release stays exempt on purpose. Tests in `accounts/tests_csrf.py`. Verify the guest flows in a browser before go-live |
| 6 | MED | MySQL root password `vengeance` is the `base.py` default and in history | **Open** — dev relies on it (no `DATABASE_URL` in `.env`). Rotate if ever reused; prod already requires `DATABASE_URL` |
| 7 | MED | Deploy blockers: no `mysqlclient`, Postgres-only assumptions, `/media/` not served | Fixed: `requirements-mysql.txt`, MySQL options in `prod.py`, nginx `/media/` |

Found and fixed while implementing the VPS work:

| Finding | Fix |
|---------|-----|
| Behind nginx every request comes from 127.0.0.1: one shared DRF throttle bucket for all anonymous users, wrong IPs in audit log | `core.middleware.ProxyRemoteAddrMiddleware` + `NUM_PROXIES=0`, enabled by `TRUST_PROXY_HEADERS=True`; nginx overwrites `X-Forwarded-For` |
| `rooms.apps.ready()` wrote to the DB on every process start (each worker, `check`, `collectstatic`); concurrent workers could create duplicate django-q schedules; errors were swallowed | Moved to a `post_migrate` handler (`rooms/apps.py`), idempotent, logged on failure |
| `wsgi.py` defaults to prod settings but `asgi.py` defaults to dev | Noted, not changed (ASGI unused) |

Business-logic flaws found in the second pass (all fixed with tests):

| Finding | Impact | Fix |
|---------|--------|-----|
| `int(float(x) * 100)` for Razorpay amounts | 6.6% of amounts under-charged by 1 paisa (1.13 became 112). Webhook reconciliation uses exact Decimal, so an early `payment.captured` was an `AMOUNT_MISMATCH`: payment marked failed and the hold released for a guest who had paid | `payments.utils.inr_to_paise` (Decimal, half-up) in order, refund and reconciliation |
| `release_expired_holds` bulk `.update()` skipped coupon release | Every abandoned hold with a coupon stranded the coupon as `applied` forever (guest loses a coupon bought with points) | Sweep releases coupons under row locks and self-heals already-stranded ones |
| Guest/superadmin cancel of a pending booking kept the coupon `applied` | Same loss | `Booking.release_coupon()` used by every path |
| `apply_coupon_to_booking` had no booking-ownership check (remove had one) | Authenticated guest could attach a coupon to another guest's pending booking (needs the UUID) | Ownership check + test |
| No bound on stay length or advance window | Anonymous search called `calculate_price` per room: `check_out=9999-12-31` costs about 1.4 s CPU per room and overflows the price column | `MAX_STAY_NIGHTS` (90) and `MAX_ADVANCE_BOOKING_DAYS` (730), env-configurable |
| Hold acquisition locked only overlapping rows | With zero rows to lock, concurrent holds can both succeed on Postgres READ COMMITTED; gap-lock deadlocks on MySQL | Lock the Room row first, as the walk-in service already does |

Open, needs a business or product decision (not changed):
- **Paid but no booking**: `ROOM_CONFLICT`, payment for a cancelled booking, and `AMOUNT_MISMATCH` only log "RECONCILIATION NEEDED". No automatic refund or alert; finance must watch the logs.
- **Superadmin cancel of a confirmed booking** does not initiate a refund or resync OTA inventory (guest cancel does refund).
- **Guest cancel** always refunds in full regardless of policy or check-in date, and is not row-locked (a double click can show a false "refund failed").
- `static/js/auth.js` is unreferenced legacy code with a hardcoded `http://127.0.0.1:8000`; safe to delete.
- **Hold creates an unused Razorpay order** for `total_price`; checkout creates its own for `payable_amount`. Wasted API call per hold and orphan orders.
- Login lockout is keyed by email only, so anyone can lock a known guest out for 15 minutes (accepted DoS).
- `asgi.py` defaults to dev settings, `wsgi.py` to prod.

Verified OK: Razorpay signature and webhook HMAC (constant-time, replay-protected), Channex
webhook fails closed in prod, role decorators on all superadmin/employeeadmin views, no raw
SQL / eval / `verify=False`, OTPs from `secrets`, `.env`/`db.sqlite3`/`media/` gitignored.

*AI-assisted scan, not a substitute for a professional penetration test.*
