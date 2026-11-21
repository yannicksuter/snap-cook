# SPDX-License-Identifier: AGPL-3.0-or-later
"""``access`` in every template: what the person on this page may do."""

from __future__ import annotations

from django.conf import settings

from accounts.identity import ANONYMOUS


def access(request) -> dict:
    return {
        "access": getattr(request, "access", ANONYMOUS),
        "mail_enabled": settings.SNAPCOOK_MAIL_ENABLED,
    }
