# SPDX-License-Identifier: AGPL-3.0-or-later
"""The visibility funnel.

This is the single most security-relevant module in the web app: every view and
endpoint that returns recipes goes through it. If it is wrong, private content
leaks everywhere at once.
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

    def test_anonymous_sees_only_public(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(
            set(visible_recipes(AnonymousUser()).values_list("slug", flat=True)),
            {"public-loaf"},
        )

    def test_other_user_does_not_see_private_recipes(self) -> None:
        """The whole point of private-by-default."""
        self.assertEqual(
            set(visible_recipes(self.bob).values_list("slug", flat=True)),
            {"public-loaf"},
        )

    def test_owner_sees_everything_they_own(self) -> None:
        self.assertEqual(
            set(visible_recipes(self.alice).values_list("slug", flat=True)),
            {"public-loaf", "unlisted-loaf", "private-loaf"},
        )

    def test_unlisted_is_excluded_from_listings(self) -> None:
        """Unlisted means 'reachable with the link', not 'browsable'."""
        self.assertNotIn(
            "unlisted-loaf",
            set(visible_recipes(self.bob).values_list("slug", flat=True)),
        )

    def test_unlisted_is_reachable_by_direct_address(self) -> None:
        self.assertIn(
            "unlisted-loaf",
            set(addressable_recipes(self.bob).values_list("slug", flat=True)),
        )


class NotFoundTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        users = get_user_model().objects
        cls.alice = users.create_user(username="alice", email="a@example.com")
        cls.bob = users.create_user(username="bob", email="b@example.com")
        cls.private = _recipe(cls.alice, "secret-loaf", Visibility.PRIVATE)

    def test_private_recipe_raises_404_for_a_stranger_not_403(self) -> None:
        """403 would confirm the slug exists.

        That leaks the existence of private content one guess at a time, which
        is why the convention is 404 everywhere a caller may not see something.
        """
        with self.assertRaises(Http404):
            get_recipe_or_404(self.bob, "secret-loaf")

    def test_owner_can_fetch_their_own_private_recipe(self) -> None:
        self.assertEqual(get_recipe_or_404(self.alice, "secret-loaf").slug, "secret-loaf")


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
