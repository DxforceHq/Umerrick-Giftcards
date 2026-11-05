"""Local development settings.

This module is intentionally permissive and uses SQLite when DATABASE_URL is
not supplied.  It must never be used by the production WSGI process.
"""

import os

from dotenv import load_dotenv

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, csv_env, database_from_url

load_dotenv(BASE_DIR / ".env", override=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-local-only-change-me")
DEBUG = True
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = csv_env(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "https://*.ngrok-free.app"
)

database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url:
    DATABASES = database_from_url(database_url)
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_REFERRER_POLICY = "same-origin"
