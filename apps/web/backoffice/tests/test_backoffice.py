# SPDX-License-Identifier: AGPL-3.0-or-later
"""The admin pages: people and their cook switch, deleting into the archive, giving
archived recipes to someone, and reading a recipe again from its kept original."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.identity import ARCHIVE_HANDLE
from accounts.testing import verified
from catalog.models import Recipe
from catalog.projection import project_recipe
from imports.models import ImportJob
from imports.tasks import read_recipe
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore

pytestmark = pytest.mark.django_db

_RECIPE = """---
title: Käsekuchen
servings: 12
lang: de
---
@Magerquark{1%kg} und @Zucker{75%g} glatt rühren.
"""


@pytest.fixture
def admin(client, settings, tmp_path, django_user_model):
    settings.SNAPCOOK_ADMIN_EMAILS = ["yannick.suter@example.com"]
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "sources"
    user = verified(
        django_user_model.objects.create_user(username="admin", email="yannick.suter@example.com"),
        cook=False,
    )
    client.force_login(user)
    return user


@pytest.fixture
def nonna(django_user_model):
    return verified(
        django_user_model.objects.create_user(username="nonna", email="nonna.rossi@example.com")
    )


@pytest.fixture
def her_recipe(settings, nonna):
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_RECIPE)
    store.commit(recipe, author=nonna.username, created_at="2026-11-20T20:00:00")
    return store, project_recipe(store, recipe.id, nonna)


def test_people_appear_by_initials_and_a_masked_address(admin, nonna, client) -> None:
    page = client.get("/admin/").content.decode()
    assert "YS" in page and "NR" in page
    assert "n•••@example.com" in page
    assert "nonna.rossi@example.com" not in page and "yannick.suter@example.com" not in page


def test_the_switch_lets_someone_cook(admin, nonna, client) -> None:
    nonna.profile.can_cook = False
    nonna.profile.save()
    client.post(f"/admin/people/{nonna.pk}/cook/", {"can_cook": "1"})
    nonna.profile.refresh_from_db()
    assert nonna.profile.can_cook
    client.post(f"/admin/people/{nonna.pk}/cook/", {"can_cook": "0"})
    nonna.profile.refresh_from_db()
    assert not nonna.profile.can_cook


def test_deleting_someone_archives_their_recipes(admin, nonna, her_recipe, client) -> None:
    store, row = her_recipe
    response = client.post(f"/admin/people/{nonna.pk}/delete/")
    assert response["Location"] == "/admin/"
    assert not get_user_model().objects.filter(pk=nonna.pk).exists()
    assert not Recipe.objects.filter(recipe_id=row.recipe_id).exists()
    assert store.head(row.recipe_id).author == ARCHIVE_HANDLE

    call_command("reindex", "--full", "--yes")
    assert not Recipe.objects.exists(), "the store itself says it has no owner"

    page = client.get("/admin/archive/").content.decode()
    assert "Käsekuchen" in page


def test_an_archived_recipe_can_be_given_to_someone(
    admin, nonna, her_recipe, client, django_user_model
) -> None:
    store, row = her_recipe
    client.post(f"/admin/people/{nonna.pk}/delete/")
    heir = verified(django_user_model.objects.create_user(username="h", email="heir@example.com"))
    client.post(f"/admin/archive/{row.recipe_id}/assign/", {"person": heir.pk})
    assert Recipe.objects.get(recipe_id=row.recipe_id).owner == heir
    assert store.head(row.recipe_id).author == heir.username
    call_command("reindex", "--full", "--yes")
    assert Recipe.objects.get(recipe_id=row.recipe_id).owner == heir
    assert "Nothing in the archive." in client.get("/admin/archive/").content.decode()


def test_you_cannot_delete_yourself(admin, client) -> None:
    client.post(f"/admin/people/{admin.pk}/delete/")
    assert get_user_model().objects.filter(pk=admin.pk).exists()


def test_an_old_author_name_still_finds_its_owner(settings, tmp_path, nonna) -> None:
    """Versions written before uids carry the old username as their author."""
    nonna.profile.former_handle = "nonna-before"
    nonna.profile.save()
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_RECIPE)
    store.commit(recipe, author="nonna-before", created_at="2026-11-01T10:00:00")
    call_command("reindex", "--full", "--yes")
    assert Recipe.objects.get(recipe_id=recipe.id).owner == nonna


# -- reading a recipe again ---------------------------------------------------------


@pytest.fixture
def inline_worker(settings, monkeypatch):
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    monkeypatch.setattr("backoffice.views.transaction.on_commit", lambda run: run(), raising=True)
    monkeypatch.setattr(
        "backoffice.views.async_task", lambda _name, job_id: read_recipe(job_id), raising=True
    )


def test_reading_again_uses_the_kept_page_not_the_link(
    admin, nonna, her_recipe, client, settings, inline_worker, monkeypatch
) -> None:
    store, row = her_recipe
    kept = settings.SNAPCOOK_SOURCES_DIR / row.recipe_id
    kept.mkdir(parents=True)
    (kept / "page.html").write_text("<html><body>Käsekuchen: Quark, Zucker</body></html>")
    ImportJob.objects.create(
        owner=nonna,
        kind="page",
        status="saved",
        source_url="https://gone.example/kaesekuchen",
        recipe_id=row.recipe_id,
    )

    def no_network(url):
        raise AssertionError("the live page must not be fetched when a copy is kept")

    monkeypatch.setattr("imports.tasks.fetch_page", no_network)

    assert "Web page" in client.get("/admin/recipes/").content.decode()
    response = client.post(f"/admin/recipes/{row.recipe_id}/read-again/")
    job = ImportJob.objects.get(replaces=row.recipe_id)
    assert response["Location"] == f"/drafts/{job.pk}/"
    assert (job.status, job.owner) == ("ready", admin)

    page = client.get(f"/drafts/{job.pk}/check/").content.decode()
    assert "Save as new version" in page
    response = client.post(
        f"/drafts/{job.pk}/check/",
        {
            "action": "save",
            "title": "Käsekuchen",
            "description": "",
            "servings": "12",
            "cooklang": job.cooklang,
        },
    )
    assert response["Location"] == "/admin/recipes/"
    head = store.head(row.recipe_id)
    assert head.author == nonna.username, "in the owner's name"
    assert len(store.history(row.recipe_id)) == 2
    assert Recipe.objects.get(recipe_id=row.recipe_id).owner == nonna
    assert not ImportJob.objects.filter(recipe_id="", replaces=row.recipe_id).exists()


def test_a_gone_link_with_nothing_kept_fails_gracefully(
    admin, nonna, her_recipe, client, settings, inline_worker, monkeypatch
) -> None:
    from imports.fetch import FetchError

    _store, row = her_recipe
    Recipe.objects.filter(pk=row.pk).update(source_url="https://gone.example/x")

    def gone(url):
        raise FetchError("fetch_failed", "404")

    monkeypatch.setattr("imports.tasks.fetch_page", gone)
    assert "Link only" in client.get("/admin/recipes/").content.decode()
    client.post(f"/admin/recipes/{row.recipe_id}/read-again/")
    job = ImportJob.objects.get(replaces=row.recipe_id)
    assert (job.status, job.problem) == ("failed", "no_source")
    assert "no longer loads" in client.get(f"/drafts/{job.pk}/").content.decode()


def test_with_nothing_at_all_there_is_nothing_to_read_again(admin, her_recipe, client) -> None:
    _store, row = her_recipe
    page = client.get("/admin/recipes/").content.decode()
    assert "No original kept" in page and "read-again" not in page
    client.post(f"/admin/recipes/{row.recipe_id}/read-again/")
    assert not ImportJob.objects.exists()


def test_deleting_a_re_read_draft_keeps_the_recipes_original(
    admin, her_recipe, client, settings, inline_worker
) -> None:
    _store, row = her_recipe
    kept = settings.SNAPCOOK_SOURCES_DIR / row.recipe_id
    kept.mkdir(parents=True)
    (kept / "text.txt").write_text("Käsekuchen: Quark, Zucker")
    client.post(f"/admin/recipes/{row.recipe_id}/read-again/")
    job = ImportJob.objects.get(replaces=row.recipe_id)
    client.post(f"/drafts/{job.pk}/delete/")
    assert (kept / "text.txt").exists()
