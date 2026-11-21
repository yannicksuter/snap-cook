# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the sign-in library (django-allauth) makes and names accounts here.

Both ways in -- Google, and an email address with a password -- end in the same
kind of account: its username is the uid (``accounts.identity``), never the
address or a name taken from it, because the username is what recipe versions
record as their author.
"""

from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings

from accounts.identity import uid_for


class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user) -> None:
        user.username = uid_for(user.email)

    def is_open_for_signup(self, request) -> bool:
        """Signing up with a password needs mail, for the verification link."""
        return settings.SNAPCOOK_MAIL_ENABLED


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin) -> bool:
        """Google has verified the address already; no mail needed."""
        return True
