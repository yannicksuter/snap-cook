# SPDX-License-Identifier: Apache-2.0
"""The words a reader may find a recipe by, beyond its title as written.

A German recipe should come up for "sugar" as well as for "Zucker", and for
"low-fat quark" once it has been translated. So the terms are every
ingredient's name as the recipe has it, its registry names in every language,
and its glossary translations, plus the recipe's title and description in every
language they have been translated into.
"""

from __future__ import annotations

from snapcook_core.registry import IngredientRegistry, default_registry
from snapcook_core.schema.recipe import Recipe

__all__ = ["search_terms"]


def search_terms(recipe: Recipe, *, registry: IngredientRegistry | None = None) -> list[str]:
    """Deduplicated, in a stable order, so a projection of it is reproducible."""
    registry = registry or default_registry()
    terms: dict[str, None] = {}

    def add(word: str | None) -> None:
        if word and word.strip():
            terms.setdefault(word.strip(), None)

    for value in (recipe.title, recipe.description):
        if value is not None:
            for _lang, text in sorted(value.values.items()):
                add(text)
    for action in recipe.actions:
        for use in action.ingredients:
            add(use.name)
            ingredient = registry.get(use.ingredient_id)
            if ingredient is not None:
                for _lang, name in sorted(ingredient.names.items()):
                    add(name)
            for _lang, words in sorted(recipe.glossary.items()):
                add(words.get(use.name))
    return list(terms)
