# SPDX-License-Identifier: AGPL-3.0-or-later
"""Django settings for snap-cook.

A single flat module driven entirely by the environment -- there is no
base/dev/prod split, because every difference between environments is already
an environment variable and a settings package would just be a second place to
look.

Environment variables
---------------------
Django
    DJANGO_SECRET_KEY       Required in production
    DJANGO_DEBUG            "0" in production (default "1")
    DJANGO_ALLOWED_HOSTS    Comma-separated. Must list every host the app is
                            reached by, or Django returns 400 DisallowedHost.

Database (a DERIVED PROJECTION -- see below)
    POSTGRES_HOST           default "localhost"
    POSTGRES_PORT           default "5432"
    POSTGRES_DB             default "snapcook"
    POSTGRES_USER           default "snapcook"
    POSTGRES_PASSWORD       default "" (required in production)

Storage
    SNAPCOOK_DATA_DIR       Root of the authoritative recipe store.
                            Default "/data" in the container, "./data" locally.

Google SSO
    GOOGLE_CLIENT_ID        From Google Cloud Console
    GOOGLE_CLIENT_SECRET

Product API
    SNAPCOOK_API_ENABLED    "1" (default) mounts /api/v1/
    SNAPCOOK_API_TOKEN_PEPPER
                            Server-side pepper for hashing user PATs.
                            Rotating it invalidates every issued token.

Ops API -- see the warning below
    SNAPCOOK_OPS_API_ENABLED    "0" (default) -- opt in deliberately
    SNAPCOOK_OPS_API_TOKEN      >=32 chars; the app refuses to boot otherwise
    SNAPCOOK_OPS_API_WRITE      "1" allows the mutating ops endpoints

LLM import
    SNAPCOOK_LLM_PROVIDER   anthropic | openai | local
    SNAPCOOK_LLM_API_KEY
    SNAPCOOK_LLM_BASE_URL   For a self-hosted inference service

Seed data
    SNAPCOOK_ALLOW_SHARE_ALIKE_DATA
                            "1" opts in to ODbL ingredient sources. Default "0"
                            keeps the shipped dataset free of copyleft
                            obligations. See THIRD_PARTY_DATA.md.

Build
    GIT_COMMIT              Baked at image build; surfaced by /up and the footer

Two invariants worth stating here, because settings is where people look
-----------------------------------------------------------------------
1. **Postgres is a cache.** The authoritative recipe store is the filesystem at
   SNAPCOOK_DATA_DIR. Every field on a `catalog` model must be derivable from
   it, and `manage.py reindex --full` must be able to rebuild the whole
   projection from scratch. Anything that cannot be derived belongs in
   `social` or `accounts`, never in `catalog`.

2. **The ops API bypasses per-user scoping.** /ops/api/versions/{hash} can dump
   any user's private recipe. Do not route /ops/api/ through a public tunnel.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default) == "1"


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------- core Django

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = _flag("DJANGO_DEBUG", "1")
ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Behind a reverse proxy (Cloudflare Tunnel), Django otherwise builds an http://
# OAuth callback URL, which then fails Google's exact redirect_uri match.
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS if host not in ("localhost", "127.0.0.1")
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ROOT_URLCONF = "snapcookweb.urls"
WSGI_APPLICATION = "snapcookweb.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Auth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # Jobs
    "django_q",
    # snap-cook. The split axis is who owns the truth, not what screen it is:
    "accounts",  # DB-authoritative: identity, preferences, API tokens
    "catalog",  # DERIVED: the Postgres projection of the file store
    "recipes",  # presentation only: the HTMX UI
    "imports",  # DB-authoritative: import jobs and drafts
    "social",  # DB-authoritative: follows, likes, comments
    "api",  # presentation only: django-ninja routers
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Registered last so it sees an authenticated request.user.
    "accounts.middleware.LoginRequiredMiddleware",
]

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
                "snapcookweb.context_processors.deployment",
            ],
        },
    },
]

# ---------------------------------------------------------------- storage

# The authoritative recipe store. This is the only thing that must be backed up;
# Postgres is reconstructible from it.
SNAPCOOK_DATA_DIR = Path(os.environ.get("SNAPCOOK_DATA_DIR", BASE_DIR.parent.parent / "data"))
SNAPCOOK_STORE_DIR = SNAPCOOK_DATA_DIR / "store"
SNAPCOOK_SOURCES_DIR = SNAPCOOK_DATA_DIR / "sources"
SNAPCOOK_LOGS_DIR = SNAPCOOK_DATA_DIR / "logs"

for _directory in (SNAPCOOK_STORE_DIR, SNAPCOOK_SOURCES_DIR, SNAPCOOK_LOGS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- database

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("POSTGRES_DB", "snapcook"),
        "USER": os.environ.get("POSTGRES_USER", "snapcook"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "CONN_MAX_AGE": 60,
    }
}

# ---------------------------------------------------------------- auth

SITE_ID = 1
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]

# SSO only for now; classic email+password and other providers come later.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True

# Credentials come from the environment, not a DB SocialApp row. Creating both
# raises MultipleObjectsReturned at login time, which is a confusing failure.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            "key": "",
        },
    }
}

# Straight to Google -- no intermediate "choose a login method" page while SSO
# is the only method.
LOGIN_URL = "/accounts/google/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# No local passwords exist, so validators would never run.
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

# ---------------------------------------------------------------- API surfaces

SNAPCOOK_API_ENABLED = _flag("SNAPCOOK_API_ENABLED", "1")
SNAPCOOK_API_TOKEN_PEPPER = os.environ.get("SNAPCOOK_API_TOKEN_PEPPER", "")

SNAPCOOK_OPS_API_ENABLED = _flag("SNAPCOOK_OPS_API_ENABLED", "0")
SNAPCOOK_OPS_API_TOKEN = os.environ.get("SNAPCOOK_OPS_API_TOKEN", "")
SNAPCOOK_OPS_API_WRITE = _flag("SNAPCOOK_OPS_API_WRITE", "0")

_OPS_TOKEN_MIN_LENGTH = 32
# Substrings, not exact matches: padding a placeholder out to 32 characters
# ("change-me-change-me-change-me-change-me") would otherwise pass the length
# check and look configured.
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "placeholder", "example", "insecure")
_TOKEN_HINT = "python -c 'import secrets; print(secrets.token_urlsafe(48))'"

if SNAPCOOK_OPS_API_ENABLED:
    # Refusing to boot is deliberate. The ops API can dump any user's private
    # recipe, so a weak token here is not a warning-level problem.
    _ops_token_lower = SNAPCOOK_OPS_API_TOKEN.lower()

    if len(SNAPCOOK_OPS_API_TOKEN) < _OPS_TOKEN_MIN_LENGTH:
        raise ImproperlyConfigured(
            "SNAPCOOK_OPS_API_ENABLED=1 requires SNAPCOOK_OPS_API_TOKEN of at least "
            f"{_OPS_TOKEN_MIN_LENGTH} characters (got {len(SNAPCOOK_OPS_API_TOKEN)}). "
            "The ops API bypasses per-user scoping, so a guessable token exposes "
            f"every private recipe. Generate one with: {_TOKEN_HINT}"
        )

    if any(marker in _ops_token_lower for marker in _PLACEHOLDER_MARKERS):
        raise ImproperlyConfigured(
            f"SNAPCOOK_OPS_API_TOKEN looks like a placeholder. Set a real secret: {_TOKEN_HINT}"
        )

    if len(set(SNAPCOOK_OPS_API_TOKEN)) < 8:
        raise ImproperlyConfigured(
            "SNAPCOOK_OPS_API_TOKEN has too little entropy (fewer than 8 distinct "
            f"characters). Generate one with: {_TOKEN_HINT}"
        )

# ---------------------------------------------------------------- jobs

Q_CLUSTER = {
    "name": "snapcook",
    "workers": 2,
    # Long enough for LLM extraction of a multi-page PDF.
    "timeout": 300,
    # MUST exceed `timeout`. If retry <= timeout, django-q re-runs a job that is
    # still executing, and an import silently runs twice. This is django-q's
    # classic footgun.
    "retry": 600,
    "max_attempts": 3,
    "orm": "default",
    "save_limit": 500,
    # Don't stampede scheduled jobs after the container has been down.
    "catch_up": False,
    "sync": False,
}

# ---------------------------------------------------------------- LLM

SNAPCOOK_LLM_PROVIDER = os.environ.get("SNAPCOOK_LLM_PROVIDER", "anthropic")
SNAPCOOK_LLM_API_KEY = os.environ.get("SNAPCOOK_LLM_API_KEY", "")
SNAPCOOK_LLM_BASE_URL = os.environ.get("SNAPCOOK_LLM_BASE_URL", "")

# ---------------------------------------------------------------- seed data

SNAPCOOK_ALLOW_SHARE_ALIKE_DATA = _flag("SNAPCOOK_ALLOW_SHARE_ALIKE_DATA", "0")

# ---------------------------------------------------------------- static

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------- i18n

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- build info

GIT_COMMIT = os.environ.get("GIT_COMMIT", "unknown")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
