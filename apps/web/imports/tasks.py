# SPDX-License-Identifier: AGPL-3.0-or-later
"""The worker's half of an import: fetch, read, normalise, keep the draft.

Runs in the django-q worker, never in a request (a load-bearing rule in
AGENTS.md: a model takes tens of seconds). A job moves queued -> reading ->
ready or failed. Every failure is recorded on the job with a code the page can
explain, so nothing is left for a reader to wonder about, and nothing raises
out of here: a raising task would be retried by django-q and read twice.
"""

from __future__ import annotations

import logging
import mimetypes

from django.db import transaction

from imports import sources
from imports.fetch import FetchError, fetch_page
from imports.models import ImportJob
from imports.page import read_page
from imports.providers import NotSetUp, ProviderError, importer
from snapcook_core.importing import ImportFile, ImportSource, normalize

__all__ = ["read_recipe", "source_for"]

logger = logging.getLogger(__name__)


def read_recipe(job_id: str) -> None:
    """Read one job's source into a draft. Safe to call twice for one job."""
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != ImportJob.Status.QUEUED:
            return  # deleted meanwhile, or already picked up
        job.status = ImportJob.Status.READING
        job.save(update_fields=["status", "updated_at"])

    try:
        source = source_for(job)
        raw = importer().extract(source)
    except (FetchError, ProviderError) as error:
        _fail(job, error.code, error.detail)
        return
    except NotSetUp as error:
        _fail(job, "not_set_up", str(error))
        return
    except Exception:
        logger.exception("import %s failed unexpectedly", job.pk)
        _fail(job, "model_failed", "unexpected error; see the worker log")
        return

    draft = normalize(raw, source)
    job.extraction = raw.model_dump(mode="json")
    job.cooklang = draft.cooklang
    job.questions = [question.model_dump(mode="json") for question in raw.questions]
    job.left_out = list(raw.left_out)
    if draft.recipe is None:
        job.status = ImportJob.Status.FAILED
        job.problem = draft.problem or "unreadable"
        job.detail = draft.detail
    else:
        job.status = ImportJob.Status.READY
    job.save()


def source_for(job: ImportJob) -> ImportSource:
    """What the job's reader gave us, fetched and loaded. Keeps a fetched page."""
    if job.replaces:
        return _kept_original(job)
    if job.kind == ImportJob.Kind.PAGE:
        return _fetched(job)
    if job.kind == ImportJob.Kind.FILES:
        files = tuple(
            ImportFile(data=path.read_bytes(), media_type=_media_type(path.name))
            for path in job.source_files()
        )
        return ImportSource(kind="files", files=files)
    return ImportSource(kind="text", text=job.source_text)


def _fetched(job: ImportJob) -> ImportSource:
    """The page behind the link, read, and kept as fetched for reading it again."""
    page = fetch_page(job.source_url)
    directory = job.source_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / sources.PAGE_HTML).write_text(page.html, encoding="utf-8")
    source = read_page(page.url, page.html)
    job.source_text = source.text
    job.save(update_fields=["source_text", "updated_at"])
    return source


def _kept_original(job: ImportJob) -> ImportSource:
    """A saved recipe's original, as it was kept: never the live page if there is a copy.

    A link may be gone by now, or show something else; the copy is what the
    recipe was read from. Only with no copy at all is the link tried, and if it
    no longer loads the job fails with a reason the admin page shows.
    """
    directory = job.source_dir()
    files = job.source_files()
    if files:
        return ImportSource(
            kind="files",
            files=tuple(
                ImportFile(data=path.read_bytes(), media_type=_media_type(path.name))
                for path in files
            ),
        )
    if (directory / sources.PAGE_HTML).is_file():
        html = (directory / sources.PAGE_HTML).read_text(encoding="utf-8")
        return read_page(job.source_url or "https://example.invalid/", html)
    for name in (sources.PAGE_TEXT, sources.PASTED_TEXT):
        if (directory / name).is_file():
            return ImportSource(kind="text", text=(directory / name).read_text(encoding="utf-8"))
    if job.source_url:
        try:
            return _fetched(job)
        except FetchError as error:
            raise FetchError("no_source", error.detail) from error
    raise FetchError("no_source", "nothing of the original was kept")


def _media_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _fail(job: ImportJob, code: str, detail: str) -> None:
    logger.warning("import %s failed: %s (%s)", job.pk, code, detail)
    job.status = ImportJob.Status.FAILED
    job.problem = code
    job.detail = detail
    job.save(update_fields=["status", "problem", "detail", "updated_at"])
