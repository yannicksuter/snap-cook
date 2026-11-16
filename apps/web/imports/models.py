# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import jobs and the drafts they produce.

DB-authoritative, like ``accounts``: a draft is work in progress that exists
nowhere else until someone saves it, and only then does a recipe reach the
store. ``reindex`` never touches this app.

The source a job read -- the page text or the uploaded files -- is retained, so
a draft can be read again when the prompt or the model improves. Files live on
disk under ``SNAPCOOK_SOURCES_DIR/<job id>/``; text lives in the row.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from ruamel.yaml import YAMLError

from snapcook_core.cooklang.frontmatter import parse_document
from snapcook_core.importing import Question
from snapcook_core.schema.provenance import Provenance


class ImportJob(models.Model):
    """One attempt to turn a page, photos or text into a recipe."""

    class Kind(models.TextChoices):
        PAGE = "page", "Link"
        FILES = "files", "Photos"
        TEXT = "text", "Text"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        READING = "reading", "Reading"
        READY = "ready", "Ready to check"
        FAILED = "failed", "Failed"
        SAVED = "saved", "Saved"

    # A UUID, not a sequence: the id appears in URLs, and a guessable one would
    # invite probing other people's drafts (the views check ownership anyway).
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_jobs"
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)

    source_url = models.URLField(max_length=2000, blank=True)
    source_text = models.TextField(blank=True, help_text="Pasted text, or the page as read")

    problem = models.CharField(max_length=32, blank=True, help_text="Why there is no draft")
    detail = models.TextField(blank=True, help_text="For whoever runs the server; never secrets")

    extraction = models.JSONField(
        null=True, blank=True, help_text="The model's reading, as returned"
    )
    cooklang = models.TextField(blank=True, help_text="The draft as it is being checked")
    questions = models.JSONField(default=list, blank=True, help_text="Questions still open")
    left_out = models.JSONField(default=list, blank=True)

    recipe_slug = models.CharField(max_length=200, blank=True, help_text="Set once saved")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} import {self.id} ({self.status})"

    @property
    def is_pending(self) -> bool:
        return self.status in (self.Status.QUEUED, self.Status.READING)

    @property
    def title(self) -> str:
        """The draft's title for lists, from the model's reading if there is one."""
        try:
            front, _ = parse_document(self.cooklang)
        except YAMLError:
            return ""
        return str(front.get("title") or "")

    def source_dir(self) -> Path:
        return Path(settings.SNAPCOOK_SOURCES_DIR) / str(self.id)

    def source_files(self) -> list[Path]:
        directory = self.source_dir()
        return sorted(directory.iterdir()) if directory.is_dir() else []

    def delete_sources(self) -> None:
        shutil.rmtree(self.source_dir(), ignore_errors=True)

    def open_questions(self) -> list[Question]:
        return [Question.model_validate(question) for question in self.questions]

    def cups(self) -> str | None:
        return (self.extraction or {}).get("cups")

    def provenance(self) -> Provenance:
        """Where the recipe came from, as the import recorded it."""
        extraction = self.extraction or {}
        return Provenance(
            origin="imported",
            source_url=self.source_url or None,
            source_title=extraction.get("source_title"),
            author=extraction.get("source_author"),
        )
