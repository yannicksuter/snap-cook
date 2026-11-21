# SPDX-License-Identifier: AGPL-3.0-or-later
"""The accounts that existed before uids: moved over, nobody locked out."""

from __future__ import annotations

import importlib

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.apps import apps

from accounts.identity import uid_for
from accounts.models import Profile

pytestmark = pytest.mark.django_db

forwards = importlib.import_module("accounts.migrations.0002_profile").forwards


def test_existing_people_get_a_uid_initials_and_keep_cooking(django_user_model) -> None:
    yannick = django_user_model.objects.create_user(
        username="yannick", email="Yannick.Suter@example.com"
    )
    SocialAccount.objects.create(user=yannick, provider="google", uid="123")
    curator = django_user_model.objects.create_user(
        username="curator", email="curator@snap-cook.local"
    )
    Profile.objects.all().delete()  # as before the migration

    forwards(apps, None)

    yannick.refresh_from_db()
    assert yannick.username == uid_for("yannick.suter@example.com")
    assert (yannick.profile.initials, yannick.profile.former_handle) == ("YS", "yannick")
    assert yannick.profile.can_cook, "had full use before, keeps it"
    assert EmailAddress.objects.get(user=yannick).verified, "Google had verified it"

    curator.refresh_from_db()
    assert curator.username == "curator", "made by a command: keeps its name"
    assert not curator.profile.can_cook
