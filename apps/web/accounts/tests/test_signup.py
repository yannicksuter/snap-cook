# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing up with an address and a password: nothing counts until the link is opened."""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from accounts.identity import uid_for

pytestmark = pytest.mark.django_db

_GOOD = "a long kitchen sentence"


@pytest.fixture
def with_mail(settings):
    settings.SNAPCOOK_MAIL_ENABLED = True


def _sign_up(client, password: str = _GOOD):
    return client.post(
        "/accounts/signup/",
        {"email": "Yannick.Suter@example.com", "password1": password, "password2": password},
    )


def test_signing_up_sends_a_link_and_counts_for_nothing_until_it_is_opened(
    client, with_mail
) -> None:
    response = _sign_up(client)
    assert response.status_code == 302
    user = get_user_model().objects.get()
    assert user.username == uid_for("yannick.suter@example.com"), "the uid, not the address"
    assert user.profile.initials == "YS"
    assert not user.profile.can_cook
    assert client.get("/settings/")["Location"].startswith("/accounts/login/")

    (message,) = mail.outbox
    assert message.to == ["yannick.suter@example.com"]
    link = re.search(r"https?://\S+/accounts/confirm-email/\S+/", message.body).group(0)
    assert "u_" not in message.body, "the mail does not show the uid"

    response = client.get("/" + link.split("/", 3)[3])
    assert response.status_code == 302
    page = client.get("/settings/").content.decode()
    assert "YS" in page and "y•••@example.com" in page
    assert "yannick.suter@example.com" not in page
    assert client.get("/add/").status_code == 403, "reads until an admin switches cooking on"


def test_a_weak_password_is_refused(client, with_mail) -> None:
    page = _sign_up(client, password="password123").content.decode()
    assert not get_user_model().objects.exists()
    assert "too common" in page or "too short" in page


def test_without_mail_only_google_is_offered(client, settings) -> None:
    settings.SNAPCOOK_MAIL_ENABLED = False
    page = client.get("/accounts/login/").content.decode()
    assert "Continue with Google" in page
    assert 'name="password"' not in page
    _sign_up(client)
    assert not get_user_model().objects.exists()


def test_the_sign_in_page_offers_both_ways(client, with_mail) -> None:
    page = client.get("/accounts/login/").content.decode()
    assert "Continue with Google" in page
    assert 'name="password"' in page and "/accounts/signup/" in page


def test_without_mail_nothing_is_sent_and_no_address_is_logged(caplog, settings) -> None:
    from django.core.mail import EmailMessage

    from accounts.mail import MailOffBackend

    sent = MailOffBackend(alias="default").send_messages(
        [EmailMessage("Confirm", "https://x/confirm/KEY/", to=["secret.person@example.com"])]
    )
    assert sent == 0
    assert "1 mail(s) not sent" in caplog.text
    assert "secret.person" not in caplog.text
