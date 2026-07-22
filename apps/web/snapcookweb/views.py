# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project-level views that belong to no app."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, JsonResponse


def up(request: HttpRequest) -> JsonResponse:
    """Liveness probe. Unauthenticated by design.

    Reports the exact commit the running image was built from, which is what
    makes "is the deploy actually live?" answerable without shell access. Note
    that this does reveal the build SHA publicly -- accepted, since the repo is
    public anyway, but it raises the obligation to patch promptly.

    Deliberately shallow: no database query, no store access. A deep check
    lives at /ops/api/health, behind auth, because a health endpoint that
    touches Postgres will report the app as down during a routine restart.
    """
    return JsonResponse({"status": "ok", "commit": settings.GIT_COMMIT})
