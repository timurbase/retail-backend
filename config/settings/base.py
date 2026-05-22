"""
RetailFlow AI — base settings.

Loaded by config/settings/{dev,prod}.py which override secrets and DEBUG.
All env vars are read via django-environ.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ---------- Core ----------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------- Apps ----------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.tenants",
    "apps.accounts",
    "apps.audit",
    "apps.suppliers",
    "apps.supplier_portal",
    "apps.products",
    "apps.documents",
    "apps.insights",
    "apps.integrations",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------- Middleware ----------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom — must come after auth so request.user is populated
    "apps.core.middleware.ActiveStoreMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------- Database ----------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://retailflow:retailflow@localhost:5432/retailflow",
    ),
}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Auth ----------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- I18N ----------
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ---------- Static / Media ----------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------- DRF ----------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "300/min",
        "otp_send": "3/min",
        "otp_verify": "10/min",
    },
}

# ---------- JWT ----------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_LIFETIME_MIN", default=30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_LIFETIME_DAYS", default=14)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.PhoneOtpTokenSerializer",
}

# ---------- Schema (OpenAPI) ----------
SPECTACULAR_SETTINGS = {
    "TITLE": "RetailFlow AI API",
    "DESCRIPTION": "Backend API for RetailFlow AI",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": "apps.accounts.models.Role.choices",
    },
}

# ---------- CORS ----------
CORS_ALLOWED_ORIGINS = [env("FRONTEND_ORIGIN", default="http://localhost:3000")]
CORS_ALLOW_CREDENTIALS = True

# ---------- Celery ----------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------- Cache (Redis) ----------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
    },
}

# ---------- App-specific ----------
OTP = {
    "LENGTH": env.int("OTP_LENGTH", default=6),
    "TTL_SECONDS": env.int("OTP_TTL_SECONDS", default=300),
    "MAX_ATTEMPTS": env.int("OTP_MAX_ATTEMPTS", default=5),
    "RATE_LIMIT_PER_HOUR": env.int("OTP_RATE_LIMIT_PER_HOUR", default=10),
}

SMS = {
    "PROVIDER": env("SMS_PROVIDER", default="console"),
    "ESKIZ_EMAIL": env("ESKIZ_EMAIL", default=""),
    "ESKIZ_PASSWORD": env("ESKIZ_PASSWORD", default=""),
    "ESKIZ_FROM": env("ESKIZ_FROM", default="4546"),
}

OPENAI = {
    "API_KEY": env("OPENAI_API_KEY", default=""),
    "DEMO_MODE": env.bool("OPENAI_DEMO_MODE", default=True),
}

SOLIQ = {
    "API_BASE": env("SOLIQ_API_BASE", default="https://api.soliq.uz"),
    "API_TOKEN": env("SOLIQ_API_TOKEN", default=""),
}

DIDOX = {
    "WEBHOOK_SECRET": env("DIDOX_WEBHOOK_SECRET", default=""),
}
