"""Shared Django settings for U_MERRICK.

Environment-specific behavior belongs in ``development.py`` or
``production.py``.  This module deliberately does not load a local .env file
so a production process only uses values supplied by its service manager.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "giftcards.apps.GiftcardsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "giftcards.auth.CaseInsensitiveModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_CALLABLE = "giftcards.auth.normalized_axes_username"

ROOT_URLCONF = "umerrick.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "umerrick.wsgi.application"
ASGI_APPLICATION = "umerrick.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-ng"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"


def csv_env(name, default=""):
    """Return a comma-separated environment value as clean strings."""

    value = os.environ.get(name, default)
    return [part.strip() for part in value.split(",") if part.strip()]


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(f"{name} must be set.")
    return value


def database_from_url(url, *, require_mysql=False):
    """Parse DATABASE_URL and apply the production MySQL defaults."""

    from django.core.exceptions import ImproperlyConfigured
    import dj_database_url

    try:
        config = dj_database_url.parse(url, conn_max_age=600, conn_health_checks=True)
    except Exception as exc:
        raise ImproperlyConfigured("DATABASE_URL is not a valid database URL.") from exc
    if require_mysql and config.get("ENGINE") != "django.db.backends.mysql":
        raise ImproperlyConfigured("Production DATABASE_URL must use MySQL (mysql://).")
    if config.get("ENGINE") == "django.db.backends.mysql":
        config.setdefault("OPTIONS", {}).update(
            {"charset": "utf8mb4", "isolation_level": "read committed"}
        )
    return {"default": config}
