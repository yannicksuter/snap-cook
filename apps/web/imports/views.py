# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding a recipe: give a link, photos or text, wait, check, save.

The request never waits for a model. Adding creates a job and hands it to the
worker (``imports.tasks.read_recipe``); the reader lands on a page that polls
until the draft is ready, and can leave and come back from Home. Checking edits
the draft's Cooklang text; only saving commits a recipe to the store, private.

Every view looks a job up through ``_job``, which only finds the reader's own.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_http_methods, require_POST
from django_q.tasks import async_task
from ruamel.yaml import YAMLError

from catalog.projection import project_recipe
from imports.forms import EXTENSIONS, DetailsForm, FilesForm, LinkForm, TextForm
from imports.models import ImportJob
from imports.providers import is_set_up
from snapcook_core.cooklang.frontmatter import parse_document
from snapcook_core.importing import apply_answer, read_draft, with_details
from snapcook_core.render import RenderOptions, build_render_model
from snapcook_core.store import FilesystemStore

# Why a job has no draft, in words a reader can act on. Codes come from
# imports.fetch, imports.providers and snapcook_core.importing.normalize.
PROBLEMS = {
    "not_set_up": gettext_lazy("Reading recipes is not set up on this server yet."),
    "not_allowed": gettext_lazy("That link leads into a private network, so it cannot be read."),
    "fetch_failed": gettext_lazy(
        "The page could not be loaded. Check the link, or paste the recipe’s text instead."
    ),
    "too_large": gettext_lazy("The page is too large to read."),
    "not_a_recipe": gettext_lazy("No recipe was found in it."),
    "unreadable": gettext_lazy("The recipe came back in a form that could not be read."),
    "refused": gettext_lazy("The reader declined this one."),
    "busy": gettext_lazy("The reading service is busy. Try again in a minute."),
    "model_failed": gettext_lazy("Reading failed. Try again in a moment."),
    "timed_out": gettext_lazy("Reading took too long and was stopped."),
}
# The worker gives up on a task after 300 s; anything pending far longer died.
_STUCK_AFTER = timedelta(minutes=10)


@require_http_methods(["GET", "POST"])
def add(request: HttpRequest) -> HttpResponse:
    """The three ways in. A valid submission becomes a job, then the waiting page."""
    set_up = is_set_up()
    forms = {"link": LinkForm(), "text": TextForm(), "files": FilesForm()}
    if request.method == "POST" and set_up:
        kind = request.POST.get("kind", "")
        if kind == "link":
            form = LinkForm(request.POST)
            if form.is_valid():
                return _start(
                    request, kind=ImportJob.Kind.PAGE, source_url=form.cleaned_data["url"]
                )
        elif kind == "text":
            form = TextForm(request.POST)
            if form.is_valid():
                return _start(
                    request, kind=ImportJob.Kind.TEXT, source_text=form.cleaned_data["text"]
                )
        elif kind == "files":
            form = FilesForm(request.POST, request.FILES)
            if form.is_valid():
                return _start(request, kind=ImportJob.Kind.FILES, files=form.cleaned_data["files"])
        else:
            raise Http404
        forms[kind] = form
    status = 200 if set_up or request.method == "GET" else 503
    return render(request, "imports/add.html", {"forms": forms, "set_up": set_up}, status=status)


def status(request: HttpRequest, job_id) -> HttpResponse:
    """The waiting page while the worker reads; HTMX polls it for the fragment."""
    job = _job(request, job_id)
    if job.is_pending and timezone.now() - job.updated_at > _STUCK_AFTER:
        job.status, job.problem = ImportJob.Status.FAILED, "timed_out"
        job.save(update_fields=["status", "problem", "updated_at"])
    if job.status == ImportJob.Status.SAVED:
        return redirect("recipes:detail", job.recipe_slug)
    if job.status == ImportJob.Status.READY:
        url = reverse("imports:review", args=[job.pk])
        if request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Redirect": url})
        return redirect(url)
    context = {"job": job, "problem": PROBLEMS.get(job.problem, PROBLEMS["model_failed"])}
    template = (
        "imports/_progress.html" if request.headers.get("HX-Request") else "imports/status.html"
    )
    return render(request, template, context)


@require_http_methods(["GET", "POST"])
def review(request: HttpRequest, job_id) -> HttpResponse:
    """Check the draft: answer its questions, fix details or text, then save."""
    job = _job(request, job_id)
    if job.status == ImportJob.Status.SAVED:
        return redirect("recipes:detail", job.recipe_slug)
    if job.is_pending or not job.cooklang:
        return redirect("imports:status", job.pk)

    form = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("answer", "dismiss"):
            _answer(request, job, action)
            return redirect("imports:review", job.pk)
        form = DetailsForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            job.cooklang = with_details(
                data["cooklang"],
                title=data["title"],
                description=data["description"],
                servings=data["servings"],
            )
            draft = read_draft(job.cooklang, cups=job.cups(), provenance=job.provenance())
            job.status = ImportJob.Status.READY if draft.recipe else ImportJob.Status.FAILED
            job.problem = "" if draft.recipe else (draft.problem or "unreadable")
            job.detail = draft.detail
            job.save()
            if action == "save" and draft.recipe is not None:
                return _save(request, job, draft.recipe)
            return redirect("imports:review", job.pk)

    draft = read_draft(job.cooklang, cups=job.cups(), provenance=job.provenance())
    if form is None:
        form = DetailsForm(initial=_details(job.cooklang))
    model = None
    if draft.recipe is not None:
        prefs = getattr(request.user, "preferences", None)
        system = getattr(prefs, "unit_system", "metric")
        options = RenderOptions(
            lang=draft.recipe.source_lang, system=system if system in ("metric", "us") else "metric"
        )
        model = build_render_model(draft.recipe, options)
    context = {
        "job": job,
        "draft": draft,
        "model": model,
        "form": form,
        "questions": list(enumerate(job.open_questions())),
        "problem": PROBLEMS.get(draft.problem or "", ""),
    }
    return render(request, "imports/review.html", context)


@require_POST
def retry(request: HttpRequest, job_id) -> HttpResponse:
    job = _job(request, job_id)
    if job.status == ImportJob.Status.FAILED:
        job.status, job.problem, job.detail = ImportJob.Status.QUEUED, "", ""
        job.save(update_fields=["status", "problem", "detail", "updated_at"])
        _enqueue(job)
    return redirect("imports:status", job.pk)


@require_POST
def delete(request: HttpRequest, job_id) -> HttpResponse:
    job = _job(request, job_id)
    job.delete_sources()
    job.delete()
    messages.success(request, _("The draft was deleted."))
    return redirect("recipes:index")


def _job(request: HttpRequest, job_id) -> ImportJob:
    job = ImportJob.objects.filter(pk=job_id, owner=request.user).first()
    if job is None:
        raise Http404
    return job


def _start(
    request: HttpRequest, *, kind: str, source_url: str = "", source_text: str = "", files=()
) -> HttpResponse:
    job = ImportJob.objects.create(
        owner=request.user, kind=kind, source_url=source_url, source_text=source_text
    )
    if files:
        directory = job.source_dir()
        directory.mkdir(parents=True, exist_ok=True)
        for number, (upload, media_type) in enumerate(files, start=1):
            with (directory / f"{number}.{EXTENSIONS[media_type]}").open("wb") as out:
                for chunk in upload.chunks():
                    out.write(chunk)
    _enqueue(job)
    return redirect("imports:status", job.pk)


def _enqueue(job: ImportJob) -> None:
    # After the commit, so the worker never looks for a job it cannot see yet.
    transaction.on_commit(lambda: async_task("imports.tasks.read_recipe", str(job.pk)))


def _answer(request: HttpRequest, job: ImportJob, action: str) -> None:
    questions = job.open_questions()
    try:
        index = int(request.POST.get("question", ""))
        question = questions[index]
    except (ValueError, IndexError):
        return
    if action == "answer":
        try:
            answer = question.answers[int(request.POST.get("answer", ""))]
        except (ValueError, IndexError):
            return
        edited = apply_answer(job.cooklang, answer)
        if edited is None:
            messages.warning(
                request, _("That answer no longer fits the text. Edit the text instead.")
            )
        else:
            job.cooklang = edited
    del job.questions[index]
    job.save(update_fields=["cooklang", "questions", "updated_at"])


def _details(cooklang: str) -> dict:
    try:
        front, _ = parse_document(cooklang)
    except YAMLError:
        front = {}
    return {
        "title": front.get("title", ""),
        "description": front.get("description", ""),
        "servings": front.get("servings"),
        "cooklang": cooklang,
    }


def _save(request: HttpRequest, job: ImportJob, recipe) -> HttpResponse:
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    store.commit(
        recipe,
        author=request.user.get_username(),
        created_at=timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
        message=f"import from {job.kind}",
        origin="imported",
    )
    with transaction.atomic():
        row = project_recipe(store, recipe.id, request.user)
        job.status, job.recipe_slug = ImportJob.Status.SAVED, row.slug
        job.save(update_fields=["status", "recipe_slug", "updated_at"])
    messages.success(request, _("Saved. Only you can see this recipe."))
    return redirect("recipes:detail", row.slug)
