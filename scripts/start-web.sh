#!/usr/bin/env bash
# Web container startup — runs migrations then gunicorn.
# Railway sets $PORT; default 8000 for local docker.
set -euo pipefail

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=3}"
: "${DJANGO_SETTINGS_MODULE:=config.settings.prod}"

export DJANGO_SETTINGS_MODULE

echo "→ Collecting static files..."
uv run python manage.py collectstatic --noinput --clear

echo "→ Running migrations..."
uv run python manage.py migrate --noinput

# Optional one-shot seed. Set SEED_ON_BOOT=1 in Railway, redeploy once,
# then unset (or leave — seed_demo is idempotent via update_or_create).
if [ "${SEED_ON_BOOT:-0}" = "1" ]; then
  echo "→ SEED_ON_BOOT=1 — populating demo data..."
  uv run python manage.py seed_demo || echo "WARN: seed_demo failed; continuing boot"
fi

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
