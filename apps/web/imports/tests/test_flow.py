# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding a recipe end to end: give, wait, check, save.

The fake reader stands in for a model (``SNAPCOOK_LLM_PROVIDER=fake``), and the
worker's task runs inline where the view would queue it. Everything else is the
real path: forms, files on disk, the draft text, the store and the catalog.
"""

from __future__ import annotations

import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Recipe
from imports import forms, views
from imports.models import ImportJob
from imports.tasks import read_recipe

pytestmark = pytest.mark.django_db

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
_PDF = b"%PDF-1.7\n" + b"0" * 128


@pytest.fixture
def cook(client, django_user_model):
    user = django_user_model.objects.create_user(username="cook", email="cook@example.com")
    client.force_login(user)
    return user


@pytest.fixture
def reader(settings, tmp_path, monkeypatch):
    """The fake model, a scratch store, and the worker running inline."""
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "sources"
    monkeypatch.setattr(views, "_enqueue", lambda job: read_recipe(str(job.pk)))


def _job() -> ImportJob:
    return ImportJob.objects.get()


def test_pasted_text_becomes_a_draft_to_check(cook, client, reader) -> None:
    response = client.post("/add/", {"kind": "text", "text": "Tomato sauce: …"})
    job = _job()
    assert response["Location"] == f"/drafts/{job.pk}/"
    assert (job.status, job.kind, job.source_text) == ("ready", "text", "Tomato sauce: …")

    page = client.get(f"/drafts/{job.pk}/check/").content.decode()
    assert "Tomato sauce" in page
    assert "How much garlic?" in page
    assert "the introduction" in page


def test_the_waiting_page_moves_on_when_the_draft_is_ready(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "x"})
    job = _job()
    assert client.get(f"/drafts/{job.pk}/")["Location"] == f"/drafts/{job.pk}/check/"
    polled = client.get(f"/drafts/{job.pk}/", HTTP_HX_REQUEST="true")
    assert polled["HX-Redirect"] == f"/drafts/{job.pk}/check/"


def test_a_pending_draft_shows_its_progress(cook, client) -> None:
    job = ImportJob.objects.create(owner=cook, kind="text", source_text="x")
    page = client.get(f"/drafts/{job.pk}/").content.decode()
    assert "Reading your recipe" in page
    assert 'hx-trigger="every 2s"' in page


def test_an_answer_edits_the_draft(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "x"})
    job = _job()
    client.post(f"/drafts/{job.pk}/check/", {"action": "answer", "question": "0", "answer": "0"})
    job.refresh_from_db()
    assert "@garlic cloves{2}" in job.cooklang
    assert job.questions == []


def test_keeping_it_as_it_is_closes_the_question(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "x"})
    job = _job()
    before = job.cooklang
    client.post(f"/drafts/{job.pk}/check/", {"action": "dismiss", "question": "0"})
    job.refresh_from_db()
    assert (job.cooklang, job.questions) == (before, [])


def test_saving_makes_a_private_recipe_for_the_reader(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "x"})
    job = _job()
    response = client.post(
        f"/drafts/{job.pk}/check/",
        {
            "action": "save",
            "title": "Nonna's sauce",
            "description": "Slow and simple.",
            "servings": "6",
            "cooklang": job.cooklang,
        },
    )
    recipe = Recipe.objects.get()
    assert response["Location"] == f"/r/{recipe.slug}/"
    assert (recipe.owner, recipe.visibility, recipe.title) == (cook, "private", "Nonna's sauce")
    job.refresh_from_db()
    assert (job.status, job.recipe_slug, job.recipe_id) == ("saved", recipe.slug, recipe.recipe_id)

    page = client.get(response["Location"]).content.decode()
    assert "Saved. Only you can see this recipe." in page
    assert "6 servings" in page


def test_photos_are_kept_as_the_source(cook, client, reader) -> None:
    upload = SimpleUploadedFile("IMG_0001.jpg", _JPEG, content_type="image/jpeg")
    client.post("/add/", {"kind": "files", "files": [upload]})
    job = _job()
    assert job.kind == "files"
    assert [path.name for path in job.source_files()] == ["1.jpg"]
    assert job.status == "ready"
    assert job.provenance().source_title == "Fake Cookbook"


def test_a_file_that_is_not_a_photo_is_refused(cook, client, reader) -> None:
    upload = SimpleUploadedFile("notes.txt", b"just words", content_type="image/jpeg")
    response = client.post("/add/", {"kind": "files", "files": [upload]})
    assert response.status_code == 200
    assert "Use a photo" in response.content.decode()
    assert not ImportJob.objects.exists()


def test_an_iphone_photo_gets_its_own_explanation(cook, client, reader) -> None:
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    upload = SimpleUploadedFile("IMG_0002.HEIC", heic, content_type="image/heic")
    page = client.post("/add/", {"kind": "files", "files": [upload]}).content.decode()
    assert "HEIC" in page


def test_a_whole_copied_page_can_be_pasted(cook, client, reader) -> None:
    # Lines up to the limit with each line break counted once; past it if the
    # CRLF a browser sends for each one counted twice.
    lines = (forms.MAX_TEXT_CHARS + 1) // 100
    text = "\r\n".join(["x" * 99] * lines)
    response = client.post("/add/", {"kind": "text", "text": text})
    job = _job()
    assert response["Location"] == f"/drafts/{job.pk}/"
    assert job.source_text == text.replace("\r\n", "\n")


def test_more_text_than_a_recipe_needs_is_refused(cook, client, reader) -> None:
    text = "x" * (forms.MAX_TEXT_CHARS + 1)
    page = client.post("/add/", {"kind": "text", "text": text}).content.decode()
    assert re.search(r'id="text-errors"[^>]*><p>That is more text than one recipe needs', page)
    assert not ImportJob.objects.exists()


def test_the_page_checks_the_same_text_limit_as_the_server(cook, client, reader) -> None:
    page = client.get("/add/", HTTP_ACCEPT_LANGUAGE="de").content.decode()
    assert f'data-max="{forms.MAX_TEXT_CHARS}"' in page
    assert 'id="computer-hint" hidden' in page


def test_a_pdf_may_be_larger_than_a_photo(cook, client, reader, monkeypatch) -> None:
    monkeypatch.setattr(forms, "MAX_PHOTO_BYTES", len(_PDF) - 1)
    pdf = SimpleUploadedFile("saved page.pdf", _PDF, content_type="application/pdf")
    client.post("/add/", {"kind": "files", "files": [pdf]})
    assert [path.name for path in _job().source_files()] == ["1.pdf"]

    photo = SimpleUploadedFile("IMG_0003.jpg", _JPEG.ljust(len(_PDF), b"\x00"))
    page = client.post("/add/", {"kind": "files", "files": [photo]}).content.decode()
    assert "Each photo can be at most" in page
    assert ImportJob.objects.count() == 1


def test_pdfs_have_limits_of_their_own_and_together(cook, client, reader, monkeypatch) -> None:
    monkeypatch.setattr(forms, "MAX_PDF_BYTES", len(_PDF) - 1)
    pdf = SimpleUploadedFile("cookbook.pdf", _PDF, content_type="application/pdf")
    assert (
        "A PDF can be at most"
        in client.post("/add/", {"kind": "files", "files": [pdf]}).content.decode()
    )

    monkeypatch.setattr(forms, "MAX_PDF_BYTES", len(_PDF))
    monkeypatch.setattr(forms, "MAX_TOTAL_BYTES", 2 * len(_PDF) - 1)
    pdfs = [
        SimpleUploadedFile(f"page {n}.pdf", _PDF, content_type="application/pdf") for n in (1, 2)
    ]
    assert (
        "Together the files can be at most"
        in client.post("/add/", {"kind": "files", "files": pdfs}).content.decode()
    )
    assert not ImportJob.objects.exists()


def test_a_link_into_the_private_network_is_refused(cook, client, reader) -> None:
    client.post("/add/", {"kind": "link", "url": "http://127.0.0.1/ops/api/settings"})
    job = _job()
    assert (job.status, job.problem) == ("failed", "not_allowed")
    page = client.get(f"/drafts/{job.pk}/").content.decode()
    assert "private network" in page


def test_unreadable_text_can_be_fixed_by_hand(cook, client, reader) -> None:
    job = ImportJob.objects.create(
        owner=cook, kind="text", status="failed", problem="unreadable",
        cooklang="---\ntitle: Soup\n---\n\nAdd @salt{1.2.3%g}.",
    )  # fmt: skip
    page = client.get(f"/drafts/{job.pk}/check/").content.decode()
    assert "could not be read" in page

    fixed = "---\ntitle: Soup\n---\n\nAdd @salt{1%g}."
    client.post(
        f"/drafts/{job.pk}/check/",
        {"action": "update", "title": "Soup", "description": "", "servings": "", "cooklang": fixed},
    )
    job.refresh_from_db()
    assert (job.status, job.problem) == ("ready", "")


def test_someone_elses_draft_does_not_exist(cook, client, django_user_model) -> None:
    other = django_user_model.objects.create_user(username="other", email="o@example.com")
    job = ImportJob.objects.create(owner=other, kind="text", source_text="secret family recipe")
    for url in (f"/drafts/{job.pk}/", f"/drafts/{job.pk}/check/"):
        assert client.get(url).status_code == 404
    assert client.post(f"/drafts/{job.pk}/delete/").status_code == 404
    assert ImportJob.objects.filter(pk=job.pk).exists()


def test_home_lists_the_drafts_waiting(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "x"})
    page = client.get("/").content.decode()
    assert "Waiting for you" in page
    assert "Ready to check" in page
    assert "Tomato sauce" in page


def test_deleting_removes_the_draft_and_its_files(cook, client, reader) -> None:
    upload = SimpleUploadedFile("page.jpg", _JPEG, content_type="image/jpeg")
    client.post("/add/", {"kind": "files", "files": [upload]})
    job = _job()
    directory = job.source_dir()
    assert directory.is_dir()
    client.post(f"/drafts/{job.pk}/delete/")
    assert not ImportJob.objects.exists()
    assert not directory.exists()


def test_without_a_reader_adding_says_it_is_not_set_up(cook, client, settings) -> None:
    settings.SNAPCOOK_LLM_PROVIDER = "anthropic"
    settings.SNAPCOOK_LLM_API_KEY = ""
    assert "not set up" in client.get("/add/").content.decode()
    response = client.post("/add/", {"kind": "text", "text": "x"})
    assert response.status_code == 503
    assert not ImportJob.objects.exists()


def test_the_view_hands_the_job_to_the_worker_after_commit(
    cook, client, settings, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    queued = []
    monkeypatch.setattr(views, "async_task", lambda *args: queued.append(args))
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/add/", {"kind": "text", "text": "x"})
    assert queued == [("imports.tasks.read_recipe", str(_job().pk))]


def test_reading_twice_reads_once(cook, reader) -> None:
    """django-q may deliver a task again; a job already read is left alone."""
    job = ImportJob.objects.create(owner=cook, kind="text", source_text="x")
    read_recipe(str(job.pk))
    job.refresh_from_db()
    first = job.updated_at
    read_recipe(str(job.pk))
    job.refresh_from_db()
    assert job.updated_at == first
