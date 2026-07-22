# SPDX-License-Identifier: AGPL-3.0-or-later
"""The /up probe.

Pins the wire contract that docker-compose healthchecks, the Unraid template and
the bug-report issue template all depend on.
"""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings


class UpTests(TestCase):
    def test_up_is_reachable_without_authentication(self) -> None:
        """A health probe that needs a login is useless as a health probe."""
        response = Client().get("/up")
        self.assertEqual(response.status_code, 200)

    def test_up_reports_status_and_commit(self) -> None:
        with override_settings(GIT_COMMIT="abc1234def"):
            payload = json.loads(Client().get("/up").content)
        self.assertEqual(payload, {"status": "ok", "commit": "abc1234def"})

    def test_up_does_not_touch_the_database(self) -> None:
        """Liveness must not depend on Postgres.

        A probe that queries the database reports the app as down during a
        routine database restart, which is exactly when you do not want the
        orchestrator killing containers. The deep check lives at
        /ops/api/health instead.
        """
        with self.assertNumQueries(0):
            Client().get("/up")
