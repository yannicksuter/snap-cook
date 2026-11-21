# SPDX-License-Identifier: AGPL-3.0-or-later
"""For tests: an account as it is once its address is confirmed."""

from __future__ import annotations

from allauth.account.models import EmailAddress

from accounts.models import Profile


def verified(user, *, cook: bool = True):
    """``user`` with a confirmed address, allowed to cook unless ``cook=False``."""
    EmailAddress.objects.update_or_create(
        user=user, email=user.email, defaults={"verified": True, "primary": True}
    )
    Profile.objects.filter(user=user).update(can_cook=cook)
    return user
