# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a translating recipe page asks: is it done yet, and try again."""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.access import visible_recipes
from snapcook_core.store import FilesystemStore
from translations.jobs import STUCK_AFTER, Progress, start
from translations.models import TranslationJob


def status(request: HttpRequest, job_id) -> HttpResponse:
    """Polled by the note on the page. Done reloads the page in the new words."""
    job, _row = _job(request, job_id)
    if job.is_running and timezone.now() - job.updated_at > STUCK_AFTER:
        job.status, job.problem = TranslationJob.Status.FAILED, "timed_out"
        job.save(update_fields=["status", "problem", "updated_at"])
    if job.status == TranslationJob.Status.DONE:
        return HttpResponse(headers={"HX-Refresh": "true"})
    if job.status == TranslationJob.Status.FAILED:
        context = {"translation": Progress("failed", job)}
        return render(request, "translations/_progress.html", context)
    return HttpResponse(status=204)  # still working: nothing to swap, keep polling


@require_POST
def retry(request: HttpRequest, job_id) -> HttpResponse:
    job, row = _job(request, job_id)
    if job.status == TranslationJob.Status.FAILED:
        head = FilesystemStore(settings.SNAPCOOK_STORE_DIR).head(job.recipe_id)
        if head is not None:
            start(request.user, job.recipe_id, job.lang, head.version_id)
    url = reverse("recipes:detail", args=[row.slug])
    return redirect(f"{url}?{urlencode({'lang': job.lang})}")


def _job(request: HttpRequest, job_id):
    """The run and its recipe, if the reader may see that recipe; 404 otherwise."""
    job = get_object_or_404(TranslationJob, pk=job_id)
    row = visible_recipes(request.user).filter(recipe_id=job.recipe_id).first()
    if row is None:
        raise Http404
    return job, row
