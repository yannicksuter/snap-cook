# SPDX-License-Identifier: AGPL-3.0-or-later
"""Template context available on every page."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

_REPO_URL = "https://github.com/yannicksuter/snap-cook"


def deployment(request: HttpRequest) -> dict[str, str]:
    """Build provenance for the footer.

    Renders the same commit that /up reports, so "which version am I looking
    at?" is answerable from the browser without curl.
    """
    commit = settings.GIT_COMMIT
    known = commit != "unknown"
    return {
        "deployed_commit": commit,
        "deployed_commit_short": commit[:7] if known else "dev",
        "deployed_commit_url": f"{_REPO_URL}/commit/{commit}" if known else "",
    }
