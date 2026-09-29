# Security audit — 2026-09-29

Daily-mode audit (8/10 confidence gate) of `bugfixes/render-deploy`, code-traced with no
live requests. Machine-readable copy: `.gstack/security-reports/2026-09-29-audit.json`
(gitignored). Not run: global-skill scan, `pip-audit` (not installed) — the dependency
CVE check is still open.

| # | Sev | Finding | Status |
|---|-----|---------|--------|
| 1 | CRIT | Gmail app passwords in git history (`e497272`, `31eef19`) and in tracked `.env.example` | Placeholder fix committed. **Open:** rotate the passwords; history still contains them (rewrite needs an explicit go-ahead) |
| 2 | CRIT | `build.sh` created superadmin with default password `Admin@1234` | Fixed: env-only, skipped when unset |
| 3 | HIGH | Google login re-activated locked/revoked staff (`accounts/adapter.py`) | Fixed + tests |
| 4 | HIGH | Console email backend hard-coded in `prod.py` (OTPs in logs, no email on VPS) | Fixed: `EMAIL_BACKEND` env; Render default unchanged. VPS env template sets SMTP |
| 5 | MED | `CsrfExemptSessionAuthentication` is the DRF default, so session-authenticated API endpoints skip CSRF | **Open** — needs the frontend to send the CSRF token on every fetch; `SameSite=Lax` limits practical risk |
| 6 | MED | MySQL root password `vengeance` is the `base.py` default and in history | **Open** — dev relies on it (no `DATABASE_URL` in `.env`). Rotate if ever reused; prod already requires `DATABASE_URL` |
| 7 | MED | Deploy blockers: no `mysqlclient`, Postgres-only assumptions, `/media/` not served | Fixed: `requirements-mysql.txt`, MySQL options in `prod.py`, nginx `/media/` |

Found and fixed while implementing the VPS work:

| Finding | Fix |
|---------|-----|
| Behind nginx every request comes from 127.0.0.1: one shared DRF throttle bucket for all anonymous users, wrong IPs in audit log | `core.middleware.ProxyRemoteAddrMiddleware` + `NUM_PROXIES=0`, enabled by `TRUST_PROXY_HEADERS=True`; nginx overwrites `X-Forwarded-For` |
| `rooms.apps.ready()` wrote to the DB on every process start (each worker, `check`, `collectstatic`); concurrent workers could create duplicate django-q schedules; errors were swallowed | Moved to a `post_migrate` handler (`rooms/apps.py`), idempotent, logged on failure |
| `wsgi.py` defaults to prod settings but `asgi.py` defaults to dev | Noted, not changed (ASGI unused) |

Verified OK: Razorpay signature and webhook HMAC (constant-time, replay-protected), Channex
webhook fails closed in prod, role decorators on all superadmin/employeeadmin views, no raw
SQL / eval / `verify=False`, OTPs from `secrets`, `.env`/`db.sqlite3`/`media/` gitignored.

*AI-assisted scan, not a substitute for a professional penetration test.*
