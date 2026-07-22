# SPDX-License-Identifier: AGPL-3.0-or-later
"""The single authorization funnel for recipe visibility.

.. warning::
   **Every view and every API endpoint that returns recipes must start from
   ``visible_recipes(user)``.** No caller may build its own queryset from
   ``Recipe.objects``.

   One funnel means visibility is enforced in one reviewable place. Scattered
   ``.filter(visibility=...)`` calls are how private content leaks: each one
   looks correct in isolation, and the one that forgets a clause is invisible
   in review. ``api/tests/test_no_leaks.py`` introspects every registered route
   and asserts this holds.

Note the 404-not-403 convention below -- a 403 confirms that a recipe exists at
that id, which is itself a disclosure.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.http import Http404

from catalog.models import Recipe, Visibility


def visible_recipes(user: object) -> QuerySet[Recipe]:
    """Recipes ``user`` is allowed to see.

    Anonymous users see public recipes only. Authenticated users additionally
    see everything they own, at any visibility.

    Unlisted is *not* included here: unlisted means "reachable if you have the
    link", so it is resolvable by id but must not appear in listings. Use
    :func:`get_recipe_or_404` for by-id access.
    """
    public = Q(visibility=Visibility.PUBLIC)
    if getattr(user, "is_authenticated", False):
        return Recipe.objects.filter(public | Q(owner=user))
    return Recipe.objects.filter(public)


def addressable_recipes(user: object) -> QuerySet[Recipe]:
    """Recipes reachable by direct id or slug, including unlisted ones."""
    reachable = Q(visibility__in=[Visibility.PUBLIC, Visibility.UNLISTED])
    if getattr(user, "is_authenticated", False):
        return Recipe.objects.filter(reachable | Q(owner=user))
    return Recipe.objects.filter(reachable)


def get_recipe_or_404(user: object, slug: str) -> Recipe:
    """Fetch by slug or raise 404.

    404 rather than 403 on a permission failure is deliberate: returning 403
    tells an unauthorized caller that the slug exists, which leaks the
    existence of private content one guess at a time.
    """
    try:
        return addressable_recipes(user).get(slug=slug)
    except Recipe.DoesNotExist as exc:
        raise Http404("No such recipe") from exc


def can_edit(user: object, recipe: Recipe) -> bool:
    """Only the owner may edit. Collaboration is a later milestone."""
    return getattr(user, "is_authenticated", False) and recipe.owner_id == user.pk
