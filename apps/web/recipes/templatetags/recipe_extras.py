# SPDX-License-Identifier: AGPL-3.0-or-later
"""Template helpers for rendering a recipe view.

Kept trivial on purpose. The interesting decision -- where an approximation sits
relative to the ingredient name -- was already made in the core render model
(``after_name``); this only reads that flag so the template does not have to.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag
def ingredient_name(ingredient) -> str:
    """The left-hand ingredient label.

    An approximation reads after the name ("salt to taste"); a measured quantity
    is shown separately on the right, so here it is just the name.
    """
    quantity = ingredient.quantity
    if quantity is not None and quantity.after_name:
        return f"{ingredient.name} {quantity.display}"
    return ingredient.name
