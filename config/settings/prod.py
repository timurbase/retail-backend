"""Production settings — Railway-aware.

Railway provides these env vars automatically:
- DATABASE_URL (when Postgres plugin attached)
- RAILWAY_PUBLIC_DOMAIN (your service's public URL)
- PORT (gunicorn binds to it)

Set these manually in the Railway dashboard:
- SECRET_KEY, ALLOWED_HOSTS, FRONTEND_ORIGIN, REDIS_URL, OPENAI_API_KEY,
  ESKIZ_*, R2_*, SOLIQ_*, DIDOX_WEBHOOK_SECRET, SENTRY_DSN
"""

import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# ---------- Cache ----------
# Redis is preferred (DRF throttling needs cross-instance shared state),
# but Railway deploys sometimes go up without REDIS_URL plumbed in. Falling
# back to LocMemCache lets the app boot and serve traffic; throttling becomes
# per-process rather than global, which is acceptable for a single-worker
# pre-launch deployment but should be fixed before scale-out.
_redis_url = env("REDIS_URL", default="").strip()
if _redis_url and not _redis_url.startswith(("redis://localhost", "redis://127.")):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "OPTIONS": {
                # Don't take the whole request path down if Redis blips.
                "IGNORE_EXCEPTIONS": True,
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
            },
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "retailflow-default",
        },
    }

# ---------- Hosts ----------
# Combine user-set ALLOWED_HOSTS with Railway's auto-provided public domain.
_user_hosts = env.list("ALLOWED_HOSTS", default=[])
_railway_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
ALLOWED_HOSTS = list({*_user_hosts, _railway_host, ".railway.app"} - {""})

# CSRF trusted origins — needs the scheme prefix
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if not h.startswith(".")
] + ["https://*.railway.app"]

# ---------- HTTPS ----------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ---------- Static files (WhiteNoise) ----------
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------- Storage ----------
# R2 only if configured; else fall back to local (Railway ephemeral disk)
_r2_bucket = env("R2_BUCKET", default="")
if _r2_bucket:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": _r2_bucket,
                "endpoint_url": env("R2_ENDPOINT"),
                "access_key": env("R2_KEY"),
                "secret_key": env("R2_SECRET"),
                "addressing_style": "virtual",
                "default_acl": "private",
                "querystring_auth": True,
                "querystring_expire": 3600,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ---------- CORS ----------
# Allow the deployed frontend; Railway sets RAILWAY_PUBLIC_DOMAIN for itself,
# but the frontend lives on a different service — set FRONTEND_ORIGIN there.
_frontend = env("FRONTEND_ORIGIN", default="")
CORS_ALLOWED_ORIGINS = [o for o in [_frontend] if o]

# ---------- Sentry ----------
if env("SENTRY_DSN", default=""):
    sentry_sdk.init(
        dsn=env("SENTRY_DSN"),
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
