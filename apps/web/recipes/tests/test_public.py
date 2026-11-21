# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading without an account: shared recipes, nothing private, nothing that costs."""

from __future__ import annotations

import pytest

from catalog.projection import project_recipe
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore
from translations.models import TranslationJob

pytestmark = pytest.mark.django_db


def _recipe(title: str, visibility: str) -> str:
    return f"""---
title: {title}
servings: 4
visibility: {visibility}
lang: de
---
@Quark{{500%g}} rühren.
"""


@pytest.fixture
def stored(settings, tmp_path, django_user_model):
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_LLM_PROVIDER = "fake"
    owner = django_user_model.objects.create_user(username="nonna", email="n@example.com")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    rows = {}
    for title, visibility in (("Geteilt", "public"), ("Geheim", "private")):
        recipe = parse_cook(_recipe(title, visibility))
        store.commit(recipe, author="nonna", created_at="2026-11-21T10:00:00")
        rows[visibility] = project_recipe(store, recipe.id, owner)
    return rows


def test_anyone_sees_the_shared_recipes(client, stored) -> None:
    page = client.get("/").content.decode()
    assert "Geteilt" in page and "Geheim" not in page
    assert "/add/" not in page, "no way in to adding for someone not signed in"
    assert "/accounts/login/" in page


def test_anyone_reads_a_shared_recipe_and_its_chart(client, stored) -> None:
    slug = stored["public"].slug
    assert client.get(f"/r/{slug}/").status_code == 200
    assert client.get(f"/r/{slug}/chart/").status_code == 200
    assert client.get(f"/r/{stored['private'].slug}/").status_code == 404


def test_reading_in_another_language_spends_nothing(client, stored) -> None:
    page = client.get(f"/r/{stored['public'].slug}/?lang=en").content.decode()
    assert not TranslationJob.objects.exists()
    assert "Translating" not in page
