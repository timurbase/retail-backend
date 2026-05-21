from .base import *  # noqa: F401,F403

DEBUG = True

# Console SMS / email backend in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Looser CORS for local dev
CORS_ALLOW_ALL_ORIGINS = True

# Enable browsable API + schema UI in dev
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)
