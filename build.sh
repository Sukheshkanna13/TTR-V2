#!/usr/bin/env bash
# Render build script — runs on every deploy
set -o errexit

echo "==> Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running database migrations..."
python manage.py migrate

echo "==> Creating superadmin (only if SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD are set)..."
if [ -z "${SUPERADMIN_EMAIL:-}" ] || [ -z "${SUPERADMIN_PASSWORD:-}" ]; then
    echo "Skipped: set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD to bootstrap a superadmin."
else
    python manage.py shell -c "
from django.contrib.auth import get_user_model
import os
User = get_user_model()
email = os.environ['SUPERADMIN_EMAIL']
password = os.environ['SUPERADMIN_PASSWORD']
if not User.objects.filter(email=email).exists():
    u = User.objects.create_superuser(email=email, password=password, full_name='Super Admin')
    u.is_active = True
    u.save()
    print(f'Superadmin created: {email}')
else:
    print(f'Superadmin already exists: {email}')
"
fi

echo "==> Build complete!"
