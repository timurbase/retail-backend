web: bash scripts/start-web.sh
worker: celery -A config worker -l info
beat: celery -A config beat -l info -S django
