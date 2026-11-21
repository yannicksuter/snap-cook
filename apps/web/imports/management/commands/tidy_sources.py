# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bring the kept originals to the current layout; the entrypoint runs it on start.

Moves the originals from ``<data>/sources`` to a mounted ``/sources``, and from
one folder per import to one per recipe (``imports.sources``). Safe to run
again: what is already in place is left alone.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from imports import sources


class Command(BaseCommand):
    help = "Move kept originals to SNAPCOOK_SOURCES_DIR, one folder per recipe."

    def handle(self, *args, **options) -> None:
        moved = sources.tidy()
        for line in moved:
            self.stdout.write(f"moved {line}")
        self.stdout.write(f"originals in {sources.root()} ({len(moved)} moved)")
