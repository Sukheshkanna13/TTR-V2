# VPS Deployment — Hostinger Ubuntu (nginx + gunicorn + systemd + MySQL)

Target: Ubuntu 24.04 VPS, one domain, MySQL on the same box. All config lives in
[`deploy/`](../deploy). The same `hotel_booking.settings.prod` module also runs on
Render; the differences are selected by environment variables only.

```
Internet ─▶ nginx :443 (TLS, /static, /media, rate limits)
              └─▶ unix socket ─▶ gunicorn (hotel_booking.wsgi)
                                     └─▶ MySQL 127.0.0.1:3306
            systemd: ttr-qcluster (django-q: hold expiry, email, loyalty sweep)
```

## 0. Before you start
- **Rotate the Gmail app passwords** that were committed to git history
  (see `docs/SECURITY-AUDIT-2026-09-29.md`). Create a fresh one for the VPS.
- Point the domain's A/AAAA record at the VPS.
- Python ≥ 3.12 is required (Django 6). Ubuntu 24.04 ships 3.12.

## 1. Server baseline
```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y python3-venv python3-dev build-essential pkg-config \
     libmysqlclient-dev mysql-server nginx certbot python3-certbot-nginx git ufw fail2ban
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
sudo adduser --system --group --home /srv/ttr ttr
```
Use SSH keys and disable password SSH login (`PasswordAuthentication no`).

## 2. Database
```bash
sudo mysql_secure_installation
sudo mysql <<'SQL'
CREATE DATABASE ttr_v2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ttr_user'@'127.0.0.1' IDENTIFIED BY 'STRONG-UNIQUE-PASSWORD';
GRANT ALL ON ttr_v2.* TO 'ttr_user'@'127.0.0.1';
SQL
```
Never reuse the local-dev root password. MySQL must listen on localhost only
(default `bind-address = 127.0.0.1`).

## 3. Application
```bash
sudo -u ttr git clone https://github.com/Sukheshkanna13/TTR-V2.git /srv/ttr/app
sudo -u ttr python3 -m venv /srv/ttr/venv
sudo -u ttr /srv/ttr/venv/bin/pip install -r /srv/ttr/app/requirements-mysql.txt

sudo mkdir -p /etc/ttr
sudo cp /srv/ttr/app/deploy/env.production.example /etc/ttr/ttr.env
sudo chown root:ttr /etc/ttr/ttr.env && sudo chmod 640 /etc/ttr/ttr.env
sudo nano /etc/ttr/ttr.env        # fill every value (SECRET_KEY, DATABASE_URL, domain, email, Razorpay…)
```
First release, run once as `ttr`:
```bash
sudo -u ttr bash -c 'set -a; source /etc/ttr/ttr.env; set +a; cd /srv/ttr/app
  /srv/ttr/venv/bin/python manage.py check --deploy
  /srv/ttr/venv/bin/python manage.py migrate       # also registers the django-q schedules
  /srv/ttr/venv/bin/python manage.py collectstatic --noinput
  /srv/ttr/venv/bin/python manage.py createsuperuser'
```
The superadmin is created interactively here. `build.sh` (Render only) no longer has a
default password; it needs `SUPERADMIN_EMAIL` and `SUPERADMIN_PASSWORD` set.

## 4. Services and nginx
```bash
sudo cp /srv/ttr/app/deploy/ttr-gunicorn.service /srv/ttr/app/deploy/ttr-qcluster.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ttr-gunicorn ttr-qcluster

sudo cp /srv/ttr/app/deploy/ttr_proxy.conf /etc/nginx/ttr_proxy.conf
sudo cp /srv/ttr/app/deploy/nginx-ttr.conf /etc/nginx/sites-available/ttr
sudo sed -i 's/example.com/YOUR-DOMAIN/g' /etc/nginx/sites-available/ttr
sudo ln -s /etc/nginx/sites-available/ttr /etc/nginx/sites-enabled/ttr && sudo rm -f /etc/nginx/sites-enabled/default
sudo certbot --nginx -d YOUR-DOMAIN -d www.YOUR-DOMAIN     # issues certs, then:
sudo nginx -t && sudo systemctl reload nginx
```
If `nginx -t` fails before certbot has issued certificates, comment out the 443 server
block, run certbot, then re-enable it.

`ttr_proxy.conf` **overwrites** `X-Forwarded-For`. `TRUST_PROXY_HEADERS=True` relies on
that: it makes DRF throttling and audit-log IPs use the real client address instead of
127.0.0.1. Never set it to True if gunicorn is reachable without nginx.

## 5. Third-party callbacks
| Service | Setting |
|---------|---------|
| Razorpay webhook | `https://DOMAIN/payments/webhook/`, events `payment.captured`, `payment.failed`; secret → `RAZORPAY_WEBHOOK_SECRET` |
| Channex webhook | `https://DOMAIN/api/ota/channex/webhook/`; secret → `CHANNEX_WEBHOOK_SECRET` (empty secret = every webhook rejected in prod) |
| Google OAuth | Redirect URI `https://DOMAIN/auth/google/login/callback/`; create the *Social application* in Django admin (client id/secret are not read from env) |

## 6. Updates and rollback
```bash
# one-time: let ttr restart only its own services
echo 'ttr ALL=(root) NOPASSWD: /bin/systemctl restart ttr-gunicorn ttr-qcluster' | sudo tee /etc/sudoers.d/ttr

sudo -u ttr /srv/ttr/app/deploy/deploy.sh main
```
The script runs `check --deploy`, migrations and `collectstatic`, restarts both services
and health-checks gunicorn. On failure it prints the previous commit to roll back to.
Migrations are not reversed automatically: take a backup first for schema changes.

## 7. Backups and monitoring
```bash
sudo -u ttr bash -c 'printf "[client]\nuser=ttr_user\npassword=STRONG-UNIQUE-PASSWORD\n" > ~/.my.cnf && chmod 600 ~/.my.cnf'
sudo -u ttr mkdir -p /srv/ttr/backups
(sudo -u ttr crontab -l 2>/dev/null; echo '15 2 * * * /srv/ttr/app/deploy/backup-db.sh >> /srv/ttr/backups/backup.log 2>&1') | sudo -u ttr crontab -
```
Also copy `/srv/ttr/backups` off the VPS (Hostinger snapshots, rclone, scp). Test a restore.
Logs: `journalctl -u ttr-gunicorn -f`, `journalctl -u ttr-qcluster -f`.

## 8. Go-live checklist
- [ ] `manage.py check --deploy` prints no warnings
- [ ] Register with a real email: the OTP arrives (not in `journalctl`)
- [ ] Hold a room, wait 10 min: hold expires (proves `ttr-qcluster` is running)
- [ ] Test-mode Razorpay payment: booking confirmed, invoice email received
- [ ] Razorpay webhook test delivery returns 200
- [ ] Upload a room image in the admin portal, then load it (`/media/` works)
- [ ] Audit log rows show real client IPs, not 127.0.0.1
- [ ] Login limit: 11 rapid POSTs to `/accounts/login/` from one IP get HTTP 503/429 from nginx
- [ ] `sudo ufw status` shows only SSH and Nginx; MySQL port 3306 not exposed
