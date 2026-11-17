# SPDX-License-Identifier: AGPL-3.0-or-later
"""Starting a translation from a recipe page, and what the page says meanwhile.

Opening a recipe in a language it was not written in translates it: the first
time, a run starts in the worker and the page says so; afterwards the words are
in the recipe and the page simply shows them. Editing a step makes only that
step stale, and the next visit translates only that.

A page view never spends money twice on the same thing. If the last run failed,
or left something it could not fit, on the version being shown, the page says so
and leaves retrying to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from django.db import IntegrityError, transaction
from django.utils import timezone
from django_q.tasks import async_task

from imports.providers import is_set_up
from snapcook_core.schema import Recipe
from snapcook_core.translating import pending_pieces
from translations.models import TranslationJob

__all__ = ["Progress", "progress_for", "start"]

# A run takes under a minute; one this old is not coming back.
STUCK_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class Progress:
    """What a recipe page says about translating it."""

    state: Literal["working", "failed", "unavailable"]
    job: TranslationJob | None = None


def progress_for(
    user, recipe_id: str, recipe: Recipe, version_id: str, lang: str
) -> Progress | None:
    """``None`` when ``recipe`` has nothing left to translate into ``lang``."""
    if not pending_pieces(recipe, lang):
        return None
    if not is_set_up():
        return Progress("unavailable")

    runs = TranslationJob.objects.filter(recipe_id=recipe_id, lang=lang)
    job = runs.order_by("-created_at").first()
    if job is not None and job.is_running:
        if timezone.now() - job.updated_at <= STUCK_AFTER:
            return Progress("working", job)
        job.status, job.problem = TranslationJob.Status.FAILED, "timed_out"
        job.save(update_fields=["status", "problem", "updated_at"])
        return Progress("failed", job)
    if job is not None and version_id in (job.from_version, job.to_version):
        if job.status == TranslationJob.Status.FAILED:
            return Progress("failed", job)
        return None  # done, with pieces it could not fit; translated as far as it goes
    return Progress("working", start(user, recipe_id, lang, version_id))


def start(user, recipe_id: str, lang: str, version_id: str) -> TranslationJob:
    """A new run, or the one another page started a moment ago."""
    try:
        with transaction.atomic():
            job = TranslationJob.objects.create(
                recipe_id=recipe_id,
                lang=lang,
                from_version=version_id,
                requested_by=user if getattr(user, "is_authenticated", False) else None,
            )
    except IntegrityError:
        return TranslationJob.objects.get(
            recipe_id=recipe_id, lang=lang, status__in=TranslationJob.RUNNING
        )
    _enqueue(job)
    return job


def _enqueue(job: TranslationJob) -> None:
    # After the commit, so the worker never looks for a run it cannot see yet.
    transaction.on_commit(lambda: async_task("translations.tasks.translate_recipe", str(job.pk)))
