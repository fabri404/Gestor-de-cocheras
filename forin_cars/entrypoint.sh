#!/usr/bin/env bash
# entrypoint.sh — se ejecuta al arrancar el contenedor web
set -euo pipefail

echo "==> [1/4] Migraciones..."
python manage.py migrate --noinput

echo "==> [2/4] Static files..."
python manage.py collectstatic --noinput --clear

echo "==> [3/4] Superadmin inicial..."
python manage.py shell << 'PYEOF'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
email    = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

if not username or not password:
    print("  DJANGO_SUPERUSER_USERNAME/PASSWORD no configurados — omitiendo creación.")
elif User.objects.filter(username=username).exists():
    print(f"  Superadmin '{username}' ya existe.")
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"  Superadmin '{username}' creado ({email}).")
PYEOF

echo "==> [4/4] Iniciando gunicorn..."
exec gunicorn forin_cars.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --forwarded-allow-ips='*' \
    --access-logfile - \
    --error-logfile -
