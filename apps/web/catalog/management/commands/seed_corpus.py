# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed the file store with the M1 corpus, then project it.

The corpus lives in ``snapcook_core.testing`` because it is a product artifact,
not test scaffolding -- the same six recipes drive the golden tests, this seed
and, later, a demo. This command commits them to the authoritative store under a
curator account and reindexes, so a fresh checkout can ``docker compose up`` and
immediately see the thesis: one recipe, many readings.

It is deliberately idempotent. The store's no-op rule means re-running commits
nothing when the content is unchanged, so seeding twice is safe.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.projection import project_recipe
from snapcook_core.store import FilesystemStore
from snapcook_core.testing import corpus_recipes

_CURATOR_USERNAME = "curator"
_CURATOR_EMAIL = "curator@snap-cook.local"
_SEED_TIME = "2026-07-20T12:00:00"


class Command(BaseCommand):
    help = "Commit the bundled corpus to the store and project it into the catalog."

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        curator, created = user_model.objects.get_or_create(
            username=_CURATOR_USERNAME,
            defaults={"email": _CURATOR_EMAIL},
        )
        if created:
            self.stdout.write(f"created curator account {_CURATOR_USERNAME!r}")

        store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
        committed = 0
        for recipe in corpus_recipes():
            before = store.head(recipe.id)
            store.commit(
                recipe,
                author=curator.get_username(),
                created_at=_SEED_TIME,
                message="seed corpus",
            )
            after = store.head(recipe.id)
            if before is None or before.version_id != after.version_id:
                committed += 1
            with transaction.atomic():
                project_recipe(store, recipe.id, curator)

        self.stdout.write(
            self.style.SUCCESS(
                f"seeded {len(corpus_recipes())} recipe(s) "
                f"({committed} new commit(s)) into {settings.SNAPCOOK_STORE_DIR}"
            )
        )
