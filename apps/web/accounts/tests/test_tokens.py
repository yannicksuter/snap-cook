# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal Access Tokens."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PAT_PREFIX, ApiToken


@override_settings(SNAPCOOK_API_TOKEN_PEPPER="test-pepper")
class ApiTokenTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="cook", email="c@example.com")

    def test_issue_returns_a_prefixed_plaintext_token(self) -> None:
        token, plaintext = ApiToken.issue(self.user, "laptop")
        self.assertTrue(plaintext.startswith(f"{PAT_PREFIX}_"))
        self.assertIn(token.prefix, plaintext)

    def test_plaintext_secret_is_never_stored(self) -> None:
        """A database dump must not yield usable tokens."""
        token, plaintext = ApiToken.issue(self.user, "laptop")
        secret = plaintext.rsplit("_", 1)[-1]
        self.assertNotIn(secret, token.token_hash)
        self.assertNotEqual(token.token_hash, secret)

    def test_hash_depends_on_the_pepper(self) -> None:
        """So a stolen database alone cannot be brute-forced offline."""
        with override_settings(SNAPCOOK_API_TOKEN_PEPPER="pepper-a"):
            a = ApiToken.hash_secret("same-secret")
        with override_settings(SNAPCOOK_API_TOKEN_PEPPER="pepper-b"):
            b = ApiToken.hash_secret("same-secret")
        self.assertNotEqual(a, b)

    def test_revoked_token_is_inactive_and_excluded(self) -> None:
        token, _ = ApiToken.issue(self.user, "laptop")
        token.revoked_at = timezone.now()
        token.save()
        self.assertFalse(token.is_active)
        self.assertNotIn(token, ApiToken.objects.active())

    def test_expired_token_is_inactive_and_excluded(self) -> None:
        token, _ = ApiToken.issue(
            self.user, "laptop", expires_at=timezone.now() - timezone.timedelta(days=1)
        )
        self.assertFalse(token.is_active)
        self.assertNotIn(token, ApiToken.objects.active())

    def test_two_tokens_never_collide(self) -> None:
        first, plain_a = ApiToken.issue(self.user, "a")
        second, plain_b = ApiToken.issue(self.user, "b")
        self.assertNotEqual(first.prefix, second.prefix)
        self.assertNotEqual(plain_a, plain_b)
