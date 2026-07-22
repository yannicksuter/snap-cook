# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild the Postgres projection from the authoritative file store.

This command is the executable proof of the architecture's central claim: that
Postgres is a cache. If `reindex --full` cannot reproduce the projection, then
something in `catalog` is not derivable from the store, and the invariant has
been broken somewhere.

Run it:
  * after restoring /data from backup
  * after editing the store outside the app (a git pull, a hand edit)
  * whenever /ops/api/consistency reports drift
  * in tests, to assert the invariant still holds

Deliberately safe by construction: it only ever touches `catalog` tables. User
accounts, preferences, API tokens and social data live in other apps and are
never in scope, so this can be run in production without fear.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Recipe, RecipeVersion
from catalog.projection import owner_resolver_from_db, project_recipe, project_store
from snapcook_core.store import FilesystemStore


class Command(BaseCommand):
    help = "Rebuild the catalog projection from the recipe store."

    def add_arguments(self, parser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--full",
            action="store_true",
            help="Truncate the projection and rebuild every recipe from scratch.",
        )
        group.add_argument(
            "--recipe",
            metavar="RECIPE_ID",
            help="Reproject a single recipe.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt (for non-interactive containers).",
        )

    def handle(self, *args, **options) -> None:
        store_dir: Path = settings.SNAPCOOK_STORE_DIR
        if not store_dir.exists():
            raise CommandError(
                f"store directory does not exist: {store_dir}\n"
                "Nothing to reindex from. Check SNAPCOOK_DATA_DIR."
            )

        if options["full"]:
            self._confirm(options["yes"])
            self._reindex_full(store_dir)
        else:
            self._reindex_one(store_dir, options["recipe"])

    def _confirm(self, skip: bool) -> None:
        if skip:
            return
        answer = input(
            "This truncates the catalog projection and rebuilds it from files.\n"
            "Accounts, preferences and social data are NOT affected. Continue? [y/N] "
        )
        if answer.strip().lower() not in {"y", "yes"}:
            raise CommandError("aborted")

    @transaction.atomic
    def _reindex_full(self, store_dir: Path) -> None:
        before = Recipe.objects.count()
        # Truncate exactly the catalog projection -- and nothing else. Accounts
        # and social data live in other apps and are never in scope here.
        RecipeVersion.objects.all().delete()
        Recipe.objects.all().delete()

        store = FilesystemStore(store_dir)
        projected, skipped = project_store(store, owner_resolver_from_db())

        self.stdout.write(
            self.style.SUCCESS(
                f"reindexed {projected} recipe(s) from {store_dir} (projection held {before})"
            )
        )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"skipped {len(skipped)} recipe(s) with no matching local owner: "
                    + ", ".join(skipped)
                )
            )

    def _reindex_one(self, store_dir: Path, recipe_id: str) -> None:
        store = FilesystemStore(store_dir)
        if not store.exists(recipe_id):
            raise CommandError(f"no such recipe in the store: {recipe_id}")

        head = store.head(recipe_id)
        owner = owner_resolver_from_db()(head.author)
        if owner is None:
            raise CommandError(
                f"recipe {recipe_id} is authored by {head.author!r}, which maps to no "
                "local user; create the user first."
            )
        with transaction.atomic():
            project_recipe(store, recipe_id, owner)
        self.stdout.write(self.style.SUCCESS(f"reindexed {recipe_id}"))
