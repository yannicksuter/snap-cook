# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every recipe keeps the original it was read from, in a folder of its own."""

from __future__ import annotations

import json
import uuid

import pytest

from accounts.testing import verified
from catalog.models import Recipe
from imports import sources, views
from imports.fetch import Page
from imports.models import ImportJob
from imports.tasks import read_recipe

pytestmark = pytest.mark.django_db

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture
def cook(client, django_user_model):
    user = verified(django_user_model.objects.create_user(username="c", email="cook@example.com"))
    client.force_login(user)
    return user


@pytest.fixture
def reader(settings, tmp_path, monkeypatch):
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "sources"
    monkeypatch.setattr(views, "_enqueue", lambda job: read_recipe(str(job.pk)))
    return tmp_path / "sources"


def _save(client, job: ImportJob) -> Recipe:
    client.post(
        f"/drafts/{job.pk}/check/",
        {
            "action": "save",
            "title": "Sauce",
            "description": "",
            "servings": "4",
            "cooklang": job.cooklang,
        },
    )
    return Recipe.objects.get()


def test_pasted_text_is_kept_with_its_recipe(cook, client, reader) -> None:
    client.post("/add/", {"kind": "text", "text": "Tomato sauce: tomatoes, garlic"})
    job = ImportJob.objects.get()
    assert (reader / "drafts" / str(job.pk) / "text.txt").is_file()
    recipe = _save(client, job)
    kept = reader / recipe.recipe_id
    assert (kept / "text.txt").read_text() == "Tomato sauce: tomatoes, garlic"
    note = json.loads((kept / "source.json").read_text())
    assert note["kind"] == "text" and note["import"] == str(job.pk)
    assert not (reader / "drafts" / str(job.pk)).exists()


def test_photos_are_kept_with_their_recipe(cook, client, reader) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("IMG_1.jpg", _JPEG, content_type="image/jpeg")
    client.post("/add/", {"kind": "files", "files": [upload]})
    recipe = _save(client, ImportJob.objects.get())
    assert (reader / recipe.recipe_id / "1.jpg").read_bytes() == _JPEG
    assert sources.original_kind(reader / recipe.recipe_id) == "files"


def test_a_link_keeps_the_page_as_it_was_fetched(cook, client, reader, monkeypatch) -> None:
    html = "<html><head><title>Sauce</title></head><body>Tomatoes, garlic.</body></html>"
    monkeypatch.setattr(
        "imports.tasks.fetch_page", lambda url: Page(url=url, html=html), raising=True
    )
    client.post("/add/", {"kind": "link", "url": "https://example.com/sauce"})
    recipe = _save(client, ImportJob.objects.get())
    kept = reader / recipe.recipe_id
    assert (kept / "page.html").read_text() == html
    assert json.loads((kept / "source.json").read_text())["url"] == "https://example.com/sauce"


def test_tidying_moves_the_old_layout_to_one_folder_per_recipe(settings, tmp_path, cook) -> None:
    """Before, originals were kept per import under <data>/sources, text in the database."""
    settings.SNAPCOOK_DATA_DIR = tmp_path / "data"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "share"
    legacy = tmp_path / "data" / "sources"
    photo = ImportJob.objects.create(
        owner=cook, kind="files", status="saved", recipe_id="rcp_PHOTO"
    )
    ImportJob.objects.create(
        owner=cook, kind="text", status="saved", recipe_id="rcp_TEXT", source_text="Quark, Zucker"
    )
    draft = ImportJob.objects.create(owner=cook, kind="files", status="ready")
    for job in (photo, draft):
        (legacy / str(job.pk)).mkdir(parents=True)
        (legacy / str(job.pk) / "1.jpg").write_bytes(_JPEG)
    (legacy / str(uuid.uuid4())).mkdir()  # no import knows it: left alone

    sources.tidy()
    share = tmp_path / "share"
    assert (share / "rcp_PHOTO" / "1.jpg").read_bytes() == _JPEG
    assert (share / "rcp_PHOTO" / "source.json").is_file()
    assert (share / "rcp_TEXT" / "text.txt").read_text() == "Quark, Zucker"
    assert (share / "drafts" / str(draft.pk) / "1.jpg").is_file()
    assert draft.source_files() == [share / "drafts" / str(draft.pk) / "1.jpg"]

    before = sorted(str(path) for path in share.rglob("*"))
    sources.tidy()
    assert sorted(str(path) for path in share.rglob("*")) == before, "safe to run on every start"
