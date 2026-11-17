# SPDX-License-Identifier: AGPL-3.0-or-later
"""A run of translating one recipe into one language.

The translation itself is not kept here: it is committed to the file store as a
new version of the recipe, where every string keeps the hash of its source
(``snapcook_core.translating``). This row only tracks the run, so a recipe page
can say "translating", and two readers opening the same recipe start one run,
not two.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

__all__ = ["TranslationJob"]


class TranslationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        WORKING = "working", "Translating"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    RUNNING = (Status.QUEUED, Status.WORKING)

    # A UUID, like an import's: the id appears in URLs.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The store's id, not a key into the catalog: the catalog is a projection
    # that ``reindex --full`` rebuilds, and a run outlives that.
    recipe_id = models.CharField(max_length=40, db_index=True)
    lang = models.CharField(max_length=16)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)

    from_version = models.CharField(max_length=72, help_text="HEAD when the run was asked for")
    to_version = models.CharField(max_length=72, blank=True, help_text="The version it committed")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    problem = models.CharField(max_length=32, blank=True)
    detail = models.TextField(blank=True, help_text="For whoever runs the server; never secrets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recipe_id", "lang"],
                condition=models.Q(status__in=["queued", "working"]),
                name="one_running_translation",
            )
        ]
        indexes = [models.Index(fields=["recipe_id", "lang", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.recipe_id} into {self.lang}: {self.status}"

    @property
    def is_running(self) -> bool:
        return self.status in self.RUNNING
