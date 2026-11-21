# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who someone is to snap-cook, without their email address showing anywhere.

A person is known by a **uid**: a keyed hash of their email address. It is their
username, and so the author of every recipe version they write. The store is
plain files that may be pushed to a git remote, so an address there would be
published; a hash keyed with a secret of this server's cannot be reversed by
guessing addresses. The address itself is kept only where the sign-in library
needs it (to send verification and reset mails) and is shown nowhere: people
appear as two or three **initials**, and the admin pages show it masked.

Roles are worked out, not stored. A verified sign-in makes a *member*, who reads
what anyone reads plus their own settings. A member *may cook* -- add, edit and
delete recipes, and have them translated, which costs API credit -- once an
admin switches that on. An *admin* is a member whose verified address is listed
in ``SNAPCOOK_ADMIN_EMAILS``; the Docker settings decide, not the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings

__all__ = [
    "ARCHIVE_HANDLE",
    "Access",
    "access_for",
    "initials_for",
    "mask",
    "normalize",
    "uid_for",
]

ARCHIVE_HANDLE = "archive"
"""The author of a recipe whose owner was deleted: no account is ever named this,
so such a recipe belongs to no one until an admin gives it to someone."""

_UID_PREFIX = "u_"


def normalize(email: str) -> str:
    """The address as compared everywhere: trimmed and lower-cased."""
    return email.strip().lower()


def uid_for(email: str) -> str:
    """``u_`` and 26 characters of a keyed hash of the address. Stable for a key."""
    digest = hmac.new(_key(), normalize(email).encode(), hashlib.sha256).digest()
    return _UID_PREFIX + base64.b32encode(digest).decode().lower()[:26]


@cache
def _key() -> bytes:
    """``SNAPCOOK_UID_KEY``, or a key made once and kept in the data folder.

    It must never change: a changed key gives a returning person a new uid. Kept
    in ``/data``, it travels with every backup of the store it belongs to.
    """
    configured = getattr(settings, "SNAPCOOK_UID_KEY", "")
    if configured:
        return configured.encode()
    path = Path(settings.SNAPCOOK_DATA_DIR) / "secrets" / "uid.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = secrets.token_hex(32)
        # Exclusive create: of two processes starting at once, one writes.
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w") as out:
                out.write(fresh)
    return path.read_text().strip().encode()


def initials_for(email: str, taken: set[str] = frozenset()) -> str:
    """Two or three letters from the address's name part: yannick.suter@… is YS.

    The first letters of the first and last parts, or the first two letters of
    a one-part name; a third letter only where needed to be different from
    ``taken``, then a digit as a last resort.
    """
    local = normalize(email).split("@", 1)[0].split("+", 1)[0]
    parts = [part for part in re.split(r"[^a-z0-9]+", local) if part] or ["x"]
    first, last = parts[0], parts[-1]
    if len(parts) > 1:
        candidates = [first[0] + last[0]] + [first[0] + last[0] + letter for letter in last[1:]]
        candidates += [first[0] + middle[0] + last[0] for middle in parts[1:-1]]
    else:
        word = first if len(first) > 1 else first + "x"
        candidates = [word[:2]] + [word[:2] + letter for letter in word[2:]]
    candidates += [first[0] + last[0] + str(digit) for digit in range(1, 10)]
    for candidate in candidates:
        if candidate.upper() not in taken:
            return candidate.upper()
    return (first[0] + secrets.token_hex(1)).upper()[:3]


def mask(email: str) -> str:
    """``y•••@gmail.com``: enough to tell people apart, not enough to write to."""
    local, _, domain = normalize(email).partition("@")
    return f"{local[:1]}•••@{domain}" if domain else "•••"


def admin_emails() -> frozenset[str]:
    return frozenset(normalize(address) for address in settings.SNAPCOOK_ADMIN_EMAILS)


@dataclass(frozen=True)
class Access:
    """What one request's person may do; see the module docstring."""

    member: bool = False
    cook: bool = False
    admin: bool = False
    initials: str = ""


ANONYMOUS = Access()


def access_for(user) -> Access:
    """Worked out from the person's verified addresses and their profile."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return ANONYMOUS
    from allauth.account.models import EmailAddress

    verified = {
        normalize(address)
        for address in EmailAddress.objects.filter(user=user, verified=True).values_list(
            "email", flat=True
        )
    }
    if not verified:
        return ANONYMOUS  # signed in somehow, but not verified: reads as anyone does
    profile = getattr(user, "profile", None)
    admin = bool(verified & admin_emails())
    return Access(
        member=True,
        cook=admin or bool(profile and profile.can_cook),
        admin=admin,
        initials=profile.initials if profile else "",
    )


def display(user) -> str:
    """How the sign-in library names a person, in mails and on its pages."""
    profile = getattr(user, "profile", None)
    return profile.initials if profile else "snap-cook"
