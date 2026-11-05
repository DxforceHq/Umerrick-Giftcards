"""Production settings.

Every security-sensitive value is required from the process environment.  A
missing value stops startup instead of silently falling back to development
behavior.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import csv_env, database_from_url, required_env

DEBUG = False
SECRET_KEY = required_env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or "change-me" in SECRET_KEY.lower() or "replace" in SECRET_KEY.lower():
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a new random production secret.")

ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain exact production hosts.")

CSRF_TRUSTED_ORIGINS = csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain the HTTPS application origin.")
if any("*" in origin or not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production CSRF trusted origins must be exact HTTPS origins.")

DATABASE_URL = required_env("DATABASE_URL")
DATABASES = database_from_url(DATABASE_URL, require_mysql=True)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
if SECURE_HSTS_SECONDS < 31536000:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be at least one year in production.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_COOKIE_AGE", "28800"))
