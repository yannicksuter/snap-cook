# SPDX-License-Identifier: AGPL-3.0-or-later
"""LoginRequiredMiddleware and its exempt prefixes.

The exempt list is security-relevant: every prefix on it is a path that receives
no protection from this middleware. Changes to it should be deliberate, so they
are pinned here.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from accounts.middleware import LoginRequiredMiddleware


class ExemptPrefixTests(TestCase):
    def test_exempt_prefixes_are_exactly_these(self) -> None:
        """A tripwire, not a tautology.

        Adding a prefix here without thinking publishes everything under it.
        If this test fails, confirm the new prefix genuinely needs to bypass
        authentication before updating the expectation.
        """
        self.assertEqual(
            LoginRequiredMiddleware.EXEMPT_PREFIXES,
            ("/accounts/", "/admin/", "/api/", "/ops/api/", "/up", "/static/"),
        )

    def test_api_surfaces_are_exempt(self) -> None:
        """API clients must get a 401 with a body, not a 302 to a Google page.

        A redirect is unfollowable by a script and, worse, returns 200 with
        HTML -- so a naive client sees success.
        """
        for path in ("/api/", "/ops/api/"):
            self.assertTrue(
                LoginRequiredMiddleware.EXEMPT_PREFIXES
                and path.startswith(LoginRequiredMiddleware.EXEMPT_PREFIXES)
            )


class GateTests(TestCase):
    def test_anonymous_user_is_redirected_to_sso(self) -> None:
        response = Client().get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("google", response["Location"])

    def test_authenticated_user_passes_through(self) -> None:
        user = get_user_model().objects.create_user(username="cook", email="c@example.com")
        client = Client()
        client.force_login(user)
        self.assertEqual(client.get("/").status_code, 200)
