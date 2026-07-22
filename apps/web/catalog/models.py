# SPDX-License-Identifier: AGPL-3.0-or-later
"""The derived Postgres projection of the file store.

.. warning::
   **Every field in this module must be derivable from SNAPCOOK_DATA_DIR.**

   Postgres is a cache. `manage.py reindex --full` truncates these tables and
   rebuilds them from the store, and `tests/test_projection_rebuildable.py`
   asserts the result is byte-identical. If you need to persist something that
   is *not* in the files -- a like, a comment, a follow, a user preference --
   it belongs in `social` or `accounts`, never here.

   That rule is what makes the whole "files are authoritative" architecture
   true rather than aspirational. It is enforceable only because this app is
   separate from the DB-authoritative ones.

These tables exist for the things a filesystem is bad at: searching, sorting,
filtering and joining. They are an index, not a source.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Visibility(models.TextChoices):
    PRIVATE = "private", "Private"
    UNLISTED = "unlisted", "Unlisted"
    PUBLIC = "public", "Public"


class Recipe(models.Model):
    """Projection of a recipe's current HEAD.

    ``recipe_id`` is the store's ULID and is the join key back to the files.
    ``slug`` is a URL convenience and is deliberately NOT the identity -- titles
    change, and lineage must survive a rename.
    """

    recipe_id = models.CharField(max_length=40, unique=True, db_index=True)
    slug = models.SlugField(max_length=140, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipes"
    )

    # --- all of the following are projected from the store, never edited here
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    lang = models.CharField(max_length=16, default="en")
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE, db_index=True
    )
    license_spdx = models.CharField(max_length=64, blank=True, default="")
    source_url = models.URLField(blank=True, default="")
    tags = models.JSONField(default=list)

    head_version_id = models.CharField(max_length=72, db_index=True)
    head_content_hash = models.CharField(max_length=72)

    # Lineage. Null parent means an original, not a fork.
    forked_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="forks"
    )

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(db_index=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "visibility"]),
            models.Index(fields=["visibility", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.recipe_id})"


class RecipeVersion(models.Model):
    """Projection of one immutable version, for history listings.

    The authoritative bytes live in the store; this row exists so that "show me
    the last 50 versions, newest first" is a query rather than a directory walk.
    """

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="versions")
    version_id = models.CharField(max_length=72, unique=True, db_index=True)
    content_hash = models.CharField(max_length=72, db_index=True)
    parents = models.JSONField(default=list)
    origin = models.CharField(max_length=24)
    author_key = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self) -> str:
        return f"{self.recipe_id}@{self.version_id[:15]}"
