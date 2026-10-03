#!/usr/bin/env bash
# Update the running app. Run as the `ttr` user from /srv/ttr/app:  ./deploy/deploy.sh [branch]
# Restarting services needs sudo (see sudoers note in docs/VPS-DEPLOYMENT.md).
set -euo pipefail

BRANCH="${1:-main}"
APP=/srv/ttr/app
VENV=/srv/ttr/venv
cd "$APP"

set -a; source /etc/ttr/ttr.env; set +a

PREV=$(git rev-parse HEAD)
echo "==> Current release: $PREV"

git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> Installing dependencies"
"$VENV/bin/pip" install -r requirements-mysql.txt

echo "==> Deploy checks"
"$VENV/bin/python" manage.py check --deploy

echo "==> Migrating"
"$VENV/bin/python" manage.py migrate --noinput

echo "==> Collecting static files"
"$VENV/bin/python" manage.py collectstatic --noinput

echo "==> Restarting services"
sudo systemctl restart ttr-gunicorn ttr-qcluster

echo "==> Health check"
sleep 3
curl -fsS -o /dev/null -H "Host: ${ALLOWED_HOSTS%%,*}" --unix-socket /run/ttr/gunicorn.sock http://localhost/ \
  && echo "OK: now at $(git rev-parse --short HEAD)" \
  || { echo "FAILED. Roll back with: git checkout $PREV && ./deploy/deploy.sh"; exit 1; }
