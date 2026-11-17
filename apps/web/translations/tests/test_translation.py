# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opening a recipe in another language translates it, once, in the owner's name.

The fake provider "translates" by putting the language in front of each piece,
and the worker's task runs inline where the page would queue it. Everything else
is the real path: the store, the commit, the projection and the page.
"""

from __future__ import annotations

import pytest

from catalog.projection import owner_resolver_from_db, project_recipe
from imports.providers import ProviderError
from imports.providers.fake import FakeImporter
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore
from translations import jobs
from translations.models import TranslationJob
from translations.tasks import translate_recipe

pytestmark = pytest.mark.django_db

_KAESEKUCHEN = """---
title: Käsekuchen
visibility: {visibility}
lang: de
---
@Magerquark{{500%g}} und @Vanillezucker{{1%Päckchen}} glatt rühren.

~{{55%min}} bei ^conventional{{175%C}} (^fan{{155%C}}) backen.
"""


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="nonna", email="nonna@example.com")


@pytest.fixture
def reader(client, django_user_model):
    user = django_user_model.objects.create_user(username="cook", email="cook@example.com")
    client.force_login(user)
    return user


@pytest.fixture
def translating(settings, tmp_path, monkeypatch):
    """The fake model, a scratch store, and the worker running inline."""
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    monkeypatch.setattr(jobs, "_enqueue", lambda job: translate_recipe(str(job.pk)))


def _stored(settings, owner, visibility: str = "public"):
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_KAESEKUCHEN.format(visibility=visibility))
    store.commit(recipe, author=owner.get_username(), created_at="2026-11-17T10:00:00")
    return store, project_recipe(store, recipe.id, owner)


def _page(client, row, lang: str) -> str:
    response = client.get(f"/r/{row.slug}/", {"lang": lang})
    assert response.status_code == 200
    return response.content.decode()


def test_opening_a_recipe_in_english_translates_it(
    translating, settings, owner, reader, client
) -> None:
    store, row = _stored(settings, owner)
    _page(client, row, "en")  # starts the run, which the inline worker finishes

    page = _page(client, row, "en")
    assert "[en] Käsekuchen" in page
    assert "[en] Magerquark" in page
    assert "[en] Päckchen" in page
    assert "175 °C conventional" in page
    assert "Translating this recipe" not in page

    head = store.head(row.recipe_id)
    assert (head.origin, head.message) == ("translated", "translate into English")
    assert "glatt rühren" in _page(client, row, "de")
    assert "[en]" not in _page(client, row, "de")


def test_the_translation_stays_in_the_owners_name(
    translating, settings, owner, reader, client
) -> None:
    # reindex takes a recipe's owner from its latest version's author.
    store, row = _stored(settings, owner)
    _page(client, row, "en")
    head = store.head(row.recipe_id)
    assert head.author == "nonna"
    assert owner_resolver_from_db()(head.author) == owner


def test_the_note_asks_until_the_translation_is_done(
    translating, settings, owner, reader, client, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "_enqueue", lambda job: None)  # the worker is slow today
    _store, row = _stored(settings, owner)
    page = _page(client, row, "en")
    assert "Translating this recipe" in page
    job = TranslationJob.objects.get()
    assert f'hx-get="/translations/{job.pk}/"' in page

    assert client.get(f"/translations/{job.pk}/").status_code == 204
    translate_recipe(str(job.pk))
    assert client.get(f"/translations/{job.pk}/")["HX-Refresh"] == "true"
    assert "Translating this recipe" not in _page(client, row, "en")


def test_reloading_does_not_retry_a_failed_translation(
    translating, settings, owner, reader, client, monkeypatch
) -> None:
    def fail(self, request):
        raise ProviderError("busy", "rate limited")

    monkeypatch.setattr(FakeImporter, "translate", fail)
    _store, row = _stored(settings, owner)
    _page(client, row, "en")
    page = _page(client, row, "en")
    assert "could not be translated" in page
    assert TranslationJob.objects.count() == 1

    monkeypatch.undo()
    monkeypatch.setattr(jobs, "_enqueue", lambda job: translate_recipe(str(job.pk)))
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    job = TranslationJob.objects.get()
    response = client.post(f"/translations/{job.pk}/retry/")
    assert response["Location"] == f"/r/{row.slug}/?lang=en"
    assert "[en] Käsekuchen" in _page(client, row, "en")


def test_the_recipes_own_language_needs_no_translation(
    translating, settings, owner, reader, client
) -> None:
    _store, row = _stored(settings, owner)
    page = _page(client, row, "de")
    assert "Translating" not in page
    assert not TranslationJob.objects.exists()


def test_without_a_reader_the_page_says_so(settings, tmp_path, owner, reader, client) -> None:
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_LLM_PROVIDER, settings.SNAPCOOK_LLM_API_KEY = "anthropic", ""
    _store, row = _stored(settings, owner)
    assert "Translating is not set up" in _page(client, row, "en")
    assert not TranslationJob.objects.exists()


def test_a_run_is_only_visible_to_readers_of_its_recipe(
    translating, settings, owner, reader, client, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "_enqueue", lambda job: None)
    _store, row = _stored(settings, owner, visibility="private")
    job = jobs.start(owner, row.recipe_id, "en", "sc1:none")
    assert client.get(f"/translations/{job.pk}/").status_code == 404
    assert client.post(f"/translations/{job.pk}/retry/").status_code == 404
