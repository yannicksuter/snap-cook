# SPDX-License-Identifier: AGPL-3.0-or-later
"""The worker's half of a translation: ask, check, commit.

Runs in the django-q worker, never in a request. The model's answer goes through
core's ``apply_translation``, which accepts a piece only while the recipe still
holds the text that was sent and refuses a step whose slots came back wrong.
The result is committed as a new version **in the owner's name**: ``reindex``
takes a recipe's owner from the author of its latest version, so a translation
authored by whoever happened to open the page would hand them the recipe.

Like an import, nothing raises out of here: a raising task is retried by
django-q, and a retry costs money.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Recipe as CatalogRecipe
from catalog.projection import project_recipe
from imports.providers import NotSetUp, ProviderError, translator
from snapcook_core.store import FilesystemStore
from snapcook_core.translating import (
    Translated,
    TranslationRequest,
    apply_translation,
    language_name,
    pending_pieces,
)
from translations.models import TranslationJob

__all__ = ["translate_recipe"]

logger = logging.getLogger(__name__)


def translate_recipe(job_id: str) -> None:
    """Translate what one run's recipe still needs. Safe to call twice."""
    with transaction.atomic():
        job = TranslationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != TranslationJob.Status.QUEUED:
            return
        job.status = TranslationJob.Status.WORKING
        job.save(update_fields=["status", "updated_at"])

    try:
        _translate(job)
    except ProviderError as error:
        _fail(job, error.code, error.detail)
    except NotSetUp as error:
        _fail(job, "not_set_up", str(error))
    except Exception:
        logger.exception("translation %s failed unexpectedly", job.pk)
        _fail(job, "model_failed", "unexpected error; see the worker log")


def _translate(job: TranslationJob) -> None:
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    head = store.head(job.recipe_id)
    if head is None:
        _fail(job, "gone", "the recipe is no longer in the store")
        return
    pieces = pending_pieces(head.recipe, job.lang)
    if pieces:
        request = TranslationRequest(head.recipe.source_lang, job.lang, tuple(pieces))
        answer = translator().translate(request)
        sent = {piece.key: piece for piece in pieces}
        done = [Translated(sent[item.key], item.text) for item in answer.pieces if item.key in sent]

        with transaction.atomic():
            # One commit at a time per recipe: the row lock orders two runs.
            row = CatalogRecipe.objects.select_for_update().get(recipe_id=job.recipe_id)
            head = store.head(job.recipe_id)
            recipe, refused = apply_translation(head.recipe, job.lang, done)
            if refused:
                logger.warning("translation %s left %s as written", job.pk, ", ".join(refused))
            record = store.commit(
                recipe,
                author=head.author,
                created_at=timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
                message=f"translate into {language_name(job.lang)}",
                origin="translated",
            )
            project_recipe(store, job.recipe_id, row.owner)
        job.to_version = record.version_id
    job.status = TranslationJob.Status.DONE
    job.save(update_fields=["status", "to_version", "updated_at"])


def _fail(job: TranslationJob, code: str, detail: str) -> None:
    logger.warning("translation %s failed: %s (%s)", job.pk, code, detail)
    job.status = TranslationJob.Status.FAILED
    job.problem = code
    job.detail = detail
    job.save(update_fields=["status", "problem", "detail", "updated_at"])
