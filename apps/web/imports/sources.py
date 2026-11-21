# SPDX-License-Identifier: AGPL-3.0-or-later
"""The originals recipes were read from, kept for as long as the recipe is.

One folder per recipe, named by its id, under ``SNAPCOOK_SOURCES_DIR`` -- on
Unraid a share of its own, mounted at ``/sources``, so the originals can be
browsed and backed up apart from the app::

    <sources>/
    ├── rcp_01J8ZQ…/            a recipe's original, as it was given
    │   ├── 1.jpg, 2.pdf        uploaded photos and PDFs
    │   ├── text.txt            pasted text
    │   ├── page.html           a link's page as it was fetched
    │   ├── page.txt            the page's text as it was read (older imports)
    │   └── source.json         what it was, from where, when
    ├── drafts/<import id>/     an import not saved yet
    └── .trash/rcp_01J8ZQ…/     a deleted recipe's original, kept for restoring

Reading a recipe again (an admin's "read again") uses what is kept here, never
the live page: a link may be gone by then, or say something else.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from imports.forms import EXTENSIONS

__all__ = ["original_kind", "keep", "root", "tidy", "trash"]

DRAFTS = "drafts"
TRASH = ".trash"
MANIFEST = "source.json"
PAGE_HTML = "page.html"
PAGE_TEXT = "page.txt"
PASTED_TEXT = "text.txt"
_FILE_SUFFIXES = {f".{extension}" for extension in EXTENSIONS.values()}


def root() -> Path:
    return Path(settings.SNAPCOOK_SOURCES_DIR)


def uploaded_files(directory: Path) -> list[Path]:
    """The photos and PDFs in a folder, in the order they were given."""
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.suffix.lower() in _FILE_SUFFIXES),
        key=lambda path: (len(path.stem), path.stem),
    )


def original_kind(directory: Path) -> str | None:
    """``files``, ``page`` or ``text``: what kept original there is, if any."""
    if uploaded_files(directory):
        return "files"
    if (directory / PAGE_HTML).is_file():
        return "page"
    if (directory / PAGE_TEXT).is_file() or (directory / PASTED_TEXT).is_file():
        return "text"
    return None


def keep(job, recipe_id: str) -> None:
    """Move a saved draft's original into its recipe's folder, with a note of it."""
    draft = root() / DRAFTS / str(job.id)
    target = root() / recipe_id
    target.mkdir(parents=True, exist_ok=True)
    if draft.is_dir():
        for path in draft.iterdir():
            if not (target / path.name).exists():
                shutil.move(str(path), target / path.name)
        shutil.rmtree(draft, ignore_errors=True)
    _write_missing_text(job, target)
    _write_manifest(job, target)


def trash(recipe_id: str) -> None:
    """A deleted recipe's original goes aside with it, never away."""
    source = root() / recipe_id
    if not source.is_dir():
        return
    bin_ = root() / TRASH
    bin_.mkdir(parents=True, exist_ok=True)
    target, count = bin_ / recipe_id, 1
    while target.exists():
        count += 1
        target = bin_ / f"{recipe_id}.{count}"
    source.rename(target)


def tidy() -> list[str]:
    """Bring older layouts to this one; safe to run on every start. Returns what moved.

    Until now the originals were kept per import, under ``<data>/sources/<import
    id>/``, with pasted text and a page's text only in the database. Now they
    are kept per recipe, possibly on a share of their own.
    """
    from imports.models import ImportJob

    moved: list[str] = []
    here = root()
    here.mkdir(parents=True, exist_ok=True)
    legacy = Path(settings.SNAPCOOK_DATA_DIR) / "sources"
    if legacy.resolve() != here.resolve() and legacy.is_dir():
        for path in legacy.iterdir():
            if not (here / path.name).exists():
                shutil.move(str(path), here / path.name)
                moved.append(f"{path} -> {here / path.name}")
        if not any(legacy.iterdir()):
            legacy.rmdir()

    for path in list(here.iterdir()):
        try:
            job_id = uuid.UUID(path.name)
        except ValueError:
            continue  # a recipe's folder, drafts/ or .trash/
        job = ImportJob.objects.filter(pk=job_id).first()
        if job is None:
            continue  # nothing says whose it is; left where it is
        target = here / job.recipe_id if job.recipe_id else here / DRAFTS / path.name
        target.mkdir(parents=True, exist_ok=True)
        for item in path.iterdir():
            if not (target / item.name).exists():
                shutil.move(str(item), target / item.name)
        shutil.rmtree(path, ignore_errors=True)
        moved.append(f"{path} -> {target}")

    for job in ImportJob.objects.filter(status=ImportJob.Status.SAVED).exclude(recipe_id=""):
        target = here / job.recipe_id
        if not (target / MANIFEST).is_file():
            target.mkdir(parents=True, exist_ok=True)
            _write_missing_text(job, target)
            _write_manifest(job, target)
    return moved


def _write_missing_text(job, target: Path) -> None:
    """Text kept only in the database so far: written out next to the rest."""
    if not job.source_text or original_kind(target) is not None:
        return
    name = PAGE_TEXT if job.kind == job.Kind.PAGE else PASTED_TEXT
    (target / name).write_text(job.source_text, encoding="utf-8")


def _write_manifest(job, target: Path) -> None:
    note = {
        "kind": job.kind,
        "url": job.source_url or None,
        "imported_at": (job.created_at or timezone.now()).isoformat(timespec="seconds"),
        "import": str(job.id),
    }
    (target / MANIFEST).write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
