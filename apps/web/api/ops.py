# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ops / diagnostics API -- /ops/api/

Exists so the server can be inspected without shell or database access: its
health and settings, and every import -- the source as uploaded, what the model
read from it, what was saved -- so the importer's quality can be checked
against its sources.

.. danger::
   **This surface deliberately ignores ownership.** ``/ops/api/recipes/{slug}``
   and ``/ops/api/imports/{id}`` return any user's private recipe. Consequences:

   * It defaults to OFF and the app refuses to boot with a weak token.
   * It answers only requests straight from the LAN or a VPN, and refuses any
     that came through a proxy or tunnel (``api.auth.direct_from_the_lan``). It
     is not nested under /api/ so a reverse proxy can still tell the two apart.
   * SNAPCOOK_OPS_API_TOKEN is the highest-value secret in the system.

Mutating endpoints additionally require SNAPCOOK_OPS_API_WRITE=1, so the common
case (read-only inspection) does not carry the ability to change anything.
"""

from __future__ import annotations

import mimetypes
import uuid

from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from api.auth import require_ops_access
from catalog.models import Recipe as CatalogRecipe
from imports.models import ImportJob
from snapcook_core.cooklang import print_cook
from snapcook_core.store import FilesystemStore


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


# -- imports and recipes ----------------------------------------------------------
# What checking the importer needs: the source as uploaded, what the model read
# from it, what a person checked and saved, and what the model left out.


class ImportSummaryOut(Schema):
    id: str
    created_at: str
    owner: str
    kind: str
    status: str
    source_url: str
    source_files: list[str]
    problem: str
    recipe_slug: str


class ImportOut(ImportSummaryOut):
    detail: str
    source_text: str
    reading: dict | None
    """The model's answer as it came back: Cooklang, questions, what it left out."""
    draft: str
    """The Cooklang as a person checked it; what was saved, if it was."""
    questions: list
    left_out: list
    saved: str | None
    """The recipe as it is stored now, if it was saved and still exists."""


class RecipeOut(Schema):
    recipe_id: str
    slug: str
    title: str
    owner: str
    visibility: str
    lang: str
    versions: int
    head: str
    origin: str
    cooklang: str


@api.get("/imports", response=list[ImportSummaryOut], summary="Recent imports, anyone's")
def imports(request, limit: int = 20) -> list[ImportSummaryOut]:
    jobs = ImportJob.objects.select_related("owner").order_by("-created_at")
    return [_summary(job) for job in jobs[: min(max(limit, 1), 200)]]


@api.get("/imports/{job_id}", response=ImportOut, summary="One import: source, reading, result")
def import_detail(request, job_id: uuid.UUID) -> ImportOut:
    job = get_object_or_404(ImportJob.objects.select_related("owner"), pk=job_id)
    row = CatalogRecipe.objects.filter(slug=job.recipe_slug).first() if job.recipe_slug else None
    return ImportOut(
        **_summary(job).dict(),
        detail=job.detail,
        source_text=job.source_text,
        reading=job.extraction,
        draft=job.cooklang,
        questions=job.questions,
        left_out=job.left_out,
        saved=_cooklang(row.recipe_id) if row is not None else None,
    )


@api.get("/imports/{job_id}/sources/{name}", summary="A source file, as uploaded")
def import_source(request, job_id: uuid.UUID, name: str) -> FileResponse:
    job = get_object_or_404(ImportJob, pk=job_id)
    files = {path.name: path for path in job.source_files()}
    if name not in files:  # by name from the job's own list: no path reaches outside it
        raise HttpError(404, "No such source file.")
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return FileResponse(files[name].open("rb"), content_type=content_type)


@api.get("/recipes/{slug}", response=RecipeOut, summary="A stored recipe, anyone's")
def recipe_detail(request, slug: str) -> RecipeOut:
    row = get_object_or_404(CatalogRecipe.objects.select_related("owner"), slug=slug)
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    head = store.head(row.recipe_id)
    if head is None:
        raise HttpError(404, "The recipe is in the catalog but not in the store; reindex.")
    return RecipeOut(
        recipe_id=row.recipe_id,
        slug=row.slug,
        title=row.title,
        owner=row.owner.get_username(),
        visibility=row.visibility,
        lang=head.recipe.source_lang,
        versions=len(store.history(row.recipe_id)),
        head=head.version_id,
        origin=head.origin,
        cooklang=print_cook(head.recipe),
    )


def _summary(job: ImportJob) -> ImportSummaryOut:
    return ImportSummaryOut(
        id=str(job.pk),
        created_at=job.created_at.isoformat(),
        owner=job.owner.get_username(),
        kind=job.kind,
        status=job.status,
        source_url=job.source_url,
        source_files=[path.name for path in job.source_files()],
        problem=job.problem,
        recipe_slug=job.recipe_slug,
    )


def _cooklang(recipe_id: str) -> str | None:
    head = FilesystemStore(settings.SNAPCOOK_STORE_DIR).head(recipe_id)
    return print_cook(head.recipe) if head is not None else None
