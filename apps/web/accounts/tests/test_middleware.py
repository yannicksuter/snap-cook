# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who may open what: anyone reads, members keep settings, cooks change, admins admin.

The exempt prefixes and the public views are security-relevant: everything on
those lists is open to the internet. Changes to them should be deliberate, so
they are pinned here.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import get_resolver

from accounts.middleware import MEMBER_VIEWS, PUBLIC_VIEWS, AccessMiddleware
from accounts.testing import verified

pytestmark = pytest.mark.django_db


def test_the_open_lists_are_exactly_these() -> None:
    """A tripwire, not a tautology: adding to these publishes a page."""
    assert AccessMiddleware.EXEMPT_PREFIXES == ("/accounts/", "/api/", "/ops/api/", "/static/")
    assert PUBLIC_VIEWS == {"recipes:index", "recipes:detail", "recipes:chart", "up"}
    assert MEMBER_VIEWS == {"accounts:settings"}


def test_the_listed_views_exist() -> None:
    """A misspelt name would quietly make a public page need a sign-in."""
    resolver = get_resolver()
    names = {name for name in resolver.reverse_dict if isinstance(name, str)}
    for namespace, (_prefix, sub) in resolver.namespace_dict.items():
        names |= {f"{namespace}:{name}" for name in sub.reverse_dict if isinstance(name, str)}
    assert PUBLIC_VIEWS | MEMBER_VIEWS <= names


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="cook", email="c@example.com")


def test_anyone_reads_without_signing_in(client) -> None:
    assert client.get("/").status_code == 200


def test_adding_sends_a_stranger_to_sign_in(client) -> None:
    response = client.get("/add/")
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=%2Fadd%2F"


def test_an_unconfirmed_account_reads_as_anyone(client, user) -> None:
    client.force_login(user)
    assert client.get("/settings/")["Location"].startswith("/accounts/login/")


def test_a_member_keeps_settings_but_does_not_cook_until_switched_on(client, user) -> None:
    client.force_login(verified(user, cook=False))
    assert client.get("/settings/").status_code == 200
    response = client.get("/add/")
    assert response.status_code == 403
    assert "switched on by an admin" in response.content.decode()


def test_a_cook_adds(client, user) -> None:
    client.force_login(verified(user))
    assert client.get("/add/").status_code == 200


def test_admin_pages_do_not_exist_for_others(client, user) -> None:
    client.force_login(verified(user))
    assert client.get("/admin/").status_code == 404


@override_settings(SNAPCOOK_ADMIN_EMAILS=["C@Example.com"])
def test_an_admin_is_who_the_docker_settings_name(client, user) -> None:
    client.force_login(verified(user, cook=False))
    assert client.get("/admin/").status_code == 200
    assert client.get("/add/").status_code == 200, "an admin may cook"


@override_settings(SNAPCOOK_ADMIN_EMAILS=["c@example.com"])
def test_an_unconfirmed_admin_address_is_no_admin(client, user) -> None:
    client.force_login(user)
    assert client.get("/admin/").status_code == 302
