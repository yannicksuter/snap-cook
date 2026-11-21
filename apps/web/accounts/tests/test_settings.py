# SPDX-License-Identifier: AGPL-3.0-or-later
"""The settings page: language and units, set once per person."""

from __future__ import annotations

import re

import pytest

from accounts.models import UserPreferences
from accounts.testing import verified

pytestmark = pytest.mark.django_db


@pytest.fixture
def cook(client, django_user_model):
    user = verified(
        django_user_model.objects.create_user(username="cook", email="cook@example.com"), cook=False
    )
    client.force_login(user)
    return user


def test_the_page_needs_a_sign_in(client) -> None:
    response = client.get("/settings/")
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=%2Fsettings%2F"


def test_looking_saves_nothing(cook, client) -> None:
    assert client.get("/settings/").status_code == 200
    assert not UserPreferences.objects.exists()


def test_a_new_reader_starts_from_the_browser_language(cook, client) -> None:
    page = client.get("/settings/", HTTP_ACCEPT_LANGUAGE="de").content.decode()
    assert "Einstellungen" in page
    assert re.search(r'<input[^>]*value="de"[^>]*checked', page), "German is preselected"


def test_saving_switches_the_language_and_confirms_in_it(cook, client) -> None:
    response = client.post("/settings/", {"language": "de", "unit_system": "us"})
    assert response.status_code == 302
    assert response["Location"] == "/settings/"

    preferences = UserPreferences.objects.get(user=cook)
    assert (preferences.language, preferences.unit_system) == ("de", "us")

    page = client.get(response["Location"]).content.decode()
    assert "Gespeichert." in page
    assert '<html lang="de"' in page


def test_a_language_the_server_does_not_speak_is_refused(cook, client) -> None:
    response = client.post("/settings/", {"language": "fr", "unit_system": "metric"})
    assert response.status_code == 200
    assert not UserPreferences.objects.exists()


def test_a_regional_variant_reads_as_its_language(cook, client) -> None:
    """A saved ``de-CH`` has no catalogue of its own and is served as ``de``."""
    UserPreferences.objects.create(user=cook, language="de-CH")
    assert '<html lang="de"' in client.get("/").content.decode()
