# SPDX-License-Identifier: AGPL-3.0-or-later
"""The visibility funnel.

This is the single most security-relevant module in the web app: every view and
endpoint that returns recipes goes through it. Every recipe is open to read, to
everyone, whatever its own visibility says; only its owner edits it.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from catalog.access import addressable_recipes, can_edit, get_recipe_or_404, visible_recipes
from catalog.models import Recipe, Visibility


def _recipe(owner, slug: str, visibility: str) -> Recipe:
    now = timezone.now()
    return Recipe.objects.create(
        recipe_id=f"rcp_{slug}",
        slug=slug,
        owner=owner,
        title=slug.title(),
        visibility=visibility,
        head_version_id=f"sc1:{'0' * 64}",
        head_content_hash=f"sc1:{'0' * 64}",
        created_at=now,
        updated_at=now,
    )


class VisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        users = get_user_model().objects
        cls.alice = users.create_user(username="alice", email="a@example.com")
        cls.bob = users.create_user(username="bob", email="b@example.com")

        cls.public = _recipe(cls.alice, "public-loaf", Visibility.PUBLIC)
        cls.unlisted = _recipe(cls.alice, "unlisted-loaf", Visibility.UNLISTED)
        cls.private = _recipe(cls.alice, "private-loaf", Visibility.PRIVATE)

    def test_everyone_reads_every_recipe(self) -> None:
        """A family cookbook: a recipe's own visibility no longer hides it."""
        from django.contrib.auth.models import AnonymousUser

        every = {"public-loaf", "unlisted-loaf", "private-loaf"}
        for reader in (AnonymousUser(), self.bob, self.alice):
            listed = set(visible_recipes(reader).values_list("slug", flat=True))
            reachable = set(addressable_recipes(reader).values_list("slug", flat=True))
            self.assertEqual((listed, reachable), (every, every))


class NotFoundTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        users = get_user_model().objects
        cls.alice = users.create_user(username="alice", email="a@example.com")
        cls.private = _recipe(cls.alice, "secret-loaf", Visibility.PRIVATE)

    def test_a_missing_recipe_is_a_404(self) -> None:
        with self.assertRaises(Http404):
            get_recipe_or_404(self.alice, "no-such-loaf")

    def test_a_stranger_reads_a_recipe_marked_private(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(get_recipe_or_404(AnonymousUser(), "secret-loaf").slug, "secret-loaf")


class EditPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        users = get_user_model().objects
        cls.alice = users.create_user(username="alice", email="a@example.com")
        cls.bob = users.create_user(username="bob", email="b@example.com")
        cls.recipe = _recipe(cls.alice, "loaf", Visibility.PUBLIC)

    def test_only_the_owner_may_edit(self) -> None:
        self.assertTrue(can_edit(self.alice, self.recipe))
        self.assertFalse(can_edit(self.bob, self.recipe))

    def test_anonymous_may_not_edit_a_public_recipe(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(can_edit(AnonymousUser(), self.recipe))
