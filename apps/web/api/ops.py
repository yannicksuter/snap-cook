# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ops / diagnostics API -- /ops/api/

Exists so the server can be inspected without shell or database access: queue
state, store-vs-database consistency, raw canonical bytes of any version.

.. danger::
   **This surface deliberately ignores ownership.** ``/ops/api/versions/{hash}``
   returns any user's private recipe. Consequences:

   * It defaults to OFF and the app refuses to boot with a weak token.
   * Do **not** route /ops/api/ through a public tunnel. Keep it LAN-only or
     behind a VPN. It is not nested under /api/ precisely so the reverse proxy
     can treat the two differently.
   * SNAPCOOK_OPS_API_TOKEN is the highest-value secret in the system.

Mutating endpoints additionally require SNAPCOOK_OPS_API_WRITE=1, so the common
case (read-only inspection) does not carry the ability to change anything.
"""

from __future__ import annotations

from django.conf import settings
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from api.auth import require_ops_access


class OpsAuth:
    """Staff session OR the shared ops bearer token."""

    def __call__(self, request):
        return require_ops_access(request) or None


api = NinjaAPI(
    version="1.0.0",
    title="snap-cook ops",
    description="Diagnostics. Do not expose publicly.",
    urls_namespace="ops",
    auth=OpsAuth(),
)


def _require_write() -> None:
    if not settings.SNAPCOOK_OPS_API_WRITE:
        raise HttpError(
            403,
            "Mutating ops endpoints are disabled. Set SNAPCOOK_OPS_API_WRITE=1 to enable.",
        )


class HealthOut(Schema):
    status: str
    commit: str
    database: bool
    store_writable: bool
    api_enabled: bool
    ops_write_enabled: bool


@api.get("/health", response=HealthOut, summary="Deep health check")
def health(request) -> HealthOut:
    """Deeper than /up: actually touches the database and the store.

    /up stays shallow on purpose -- a liveness probe that queries Postgres
    reports the app as down during a routine database restart.
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_ok = True
    except Exception:  # noqa: BLE001 - health must report, never raise
        database_ok = False

    store = settings.SNAPCOOK_STORE_DIR
    try:
        probe = store / ".write-probe"
        probe.touch()
        probe.unlink()
        store_ok = True
    except OSError:
        store_ok = False

    return HealthOut(
        status="ok" if (database_ok and store_ok) else "degraded",
        commit=settings.GIT_COMMIT,
        database=database_ok,
        store_writable=store_ok,
        api_enabled=settings.SNAPCOOK_API_ENABLED,
        ops_write_enabled=settings.SNAPCOOK_OPS_API_WRITE,
    )


class SettingsOut(Schema):
    api_enabled: bool
    ops_api_enabled: bool
    ops_write_enabled: bool
    allow_share_alike_data: bool
    llm_provider: str
    # Presence only. Never the values.
    secrets_configured: dict[str, bool]


@api.get("/settings", response=SettingsOut, summary="Effective flags (redacted)")
def effective_settings(request) -> SettingsOut:
    """Report configuration state without ever emitting a secret value.

    Answers "is this actually configured?" -- the usual reason for wanting to
    read settings remotely -- without turning the ops token into a way to
    exfiltrate every other credential.
    """
    return SettingsOut(
        api_enabled=settings.SNAPCOOK_API_ENABLED,
        ops_api_enabled=settings.SNAPCOOK_OPS_API_ENABLED,
        ops_write_enabled=settings.SNAPCOOK_OPS_API_WRITE,
        allow_share_alike_data=settings.SNAPCOOK_ALLOW_SHARE_ALIKE_DATA,
        llm_provider=settings.SNAPCOOK_LLM_PROVIDER,
        secrets_configured={
            "google_client_id": bool(
                settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"]
            ),
            "google_client_secret": bool(
                settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["secret"]
            ),
            "api_token_pepper": bool(settings.SNAPCOOK_API_TOKEN_PEPPER),
            "ops_api_token": bool(settings.SNAPCOOK_OPS_API_TOKEN),
            "llm_api_key": bool(settings.SNAPCOOK_LLM_API_KEY),
        },
    )
