# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal access tokens authenticate whatever characters their secret holds."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from accounts.models import ApiToken
from api.auth import PatAuth

pytestmark = pytest.mark.django_db


@pytest.fixture
def cook(django_user_model):
    return django_user_model.objects.create_user(username="cook", email="cook@example.com")


def _authenticate(token: str):
    return PatAuth().authenticate(RequestFactory().get("/api/v1/"), token)


def test_a_secret_with_underscores_authenticates(cook, monkeypatch) -> None:
    """``token_urlsafe`` draws from an alphabet with ``_``: about half of all secrets have one.

    Splitting the whole token on ``_`` used to reject every one of them.
    """
    monkeypatch.setattr("accounts.models.secrets.token_urlsafe", lambda _: "ab_cd_ef_gh")
    _, plaintext = ApiToken.issue(cook, "phone")
    assert _authenticate(plaintext) == cook


def test_a_wrong_secret_is_refused(cook) -> None:
    _, plaintext = ApiToken.issue(cook, "phone")
    assert _authenticate(plaintext + "x") is None


def test_a_token_from_elsewhere_is_refused(cook) -> None:
    ApiToken.issue(cook, "phone")
    assert _authenticate("ghp_0123456789abcdef") is None
