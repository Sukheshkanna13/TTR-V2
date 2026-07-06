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

echo "==> Creating superadmin (skips if already exists)..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
import os
email = os.environ.get('SUPERADMIN_EMAIL', 'admin@templetowns.com')
password = os.environ.get('SUPERADMIN_PASSWORD', 'Admin@1234')
if not User.objects.filter(email=email).exists():
    u = User.objects.create_superuser(email=email, password=password, full_name='Super Admin')
    u.is_active = True
    u.save()
    print(f'Superadmin created: {email}')
else:
    print(f'Superadmin already exists: {email}')
"

echo "==> Build complete!"
