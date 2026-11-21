# SPDX-License-Identifier: AGPL-3.0-or-later
"""uids, initials and masked addresses: how a person appears without their address."""

from __future__ import annotations

import pytest

from accounts import identity
from accounts.identity import initials_for, mask, uid_for


@pytest.fixture(autouse=True)
def key(settings):
    settings.SNAPCOOK_UID_KEY = "test-key"
    identity._key.cache_clear()
    yield
    identity._key.cache_clear()


def test_a_uid_is_a_keyed_hash_of_the_address(settings) -> None:
    uid = uid_for("yannick.suter@gmail.com")
    assert uid.startswith("u_") and len(uid) == 28
    assert "yannick" not in uid
    assert uid_for("  Yannick.Suter@Gmail.com ") == uid, "the same address, however written"
    settings.SNAPCOOK_UID_KEY = "another-key"
    identity._key.cache_clear()
    assert uid_for("yannick.suter@gmail.com") != uid, "without the key, no one can rebuild it"


def test_without_a_configured_key_one_is_made_once_and_kept(settings, tmp_path) -> None:
    settings.SNAPCOOK_UID_KEY = ""
    settings.SNAPCOOK_DATA_DIR = tmp_path
    identity._key.cache_clear()
    first = uid_for("a@example.com")
    assert (tmp_path / "secrets" / "uid.key").stat().st_mode & 0o777 == 0o600
    identity._key.cache_clear()
    assert uid_for("a@example.com") == first


@pytest.mark.parametrize(
    ("email", "taken", "initials"),
    [
        ("yannick.suter@gmail.com", set(), "YS"),
        ("anna-maria_meier@example.com", set(), "AM"),
        ("nonna@example.com", set(), "NO"),
        ("nonna+recipes@example.com", set(), "NO"),
        ("yannick.suter@gmail.com", {"YS"}, "YSU"),
        ("yannick.suter@gmail.com", {"YS", "YSU", "YST", "YSE", "YSR"}, "YS1"),
        ("nonna@example.com", {"NO"}, "NON"),
        ("x@example.com", set(), "XX"),
    ],
)
def test_initials_come_from_the_name_part(email, taken, initials) -> None:
    assert initials_for(email, taken) == initials


def test_a_masked_address_tells_people_apart_but_cannot_be_written_to() -> None:
    assert mask("Yannick.Suter@gmail.com") == "y•••@gmail.com"
    assert mask("") == "•••"
