#!/usr/bin/env bash
# Web container startup — runs migrations then gunicorn.
# Railway sets $PORT; default 8000 for local docker.
set -euo pipefail

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=3}"
: "${DJANGO_SETTINGS_MODULE:=config.settings.prod}"

export DJANGO_SETTINGS_MODULE

echo "→ Running migrations..."
uv run python manage.py migrate --noinput

echo "→ Starting gunicorn on :$PORT with $WEB_CONCURRENCY workers..."
exec uv run gunicorn config.wsgi:application \
  --bind "0.0.0.0:$PORT" \
  --workers "$WEB_CONCURRENCY" \
  --worker-class gthread \
  --threads 4 \
  --timeout 90 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
