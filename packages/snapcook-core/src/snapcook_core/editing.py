# SPDX-License-Identifier: Apache-2.0
"""Editing a saved recipe as text: a new version of the same recipe.

A person edits the recipe's Cooklang, in the language it was written in. Read
back, that text is a recipe with a new id, no translations and default
provenance, because Cooklang carries none of them. :func:`revise` puts them
back: the same id, visibility, source and glossary, and every translation whose
source string did not change. An edited step loses only its own translation,
and the next translation run redoes only that (``snapcook_core.translating``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ruamel.yaml import YAMLError

from snapcook_core.cooklang import parse_cook
from snapcook_core.cooklang.frontmatter import dump_frontmatter, parse_document
from snapcook_core.errors import SnapcookError
from snapcook_core.importing.normalize import UNREADABLE, tidy_amounts
from snapcook_core.registry import IngredientRegistry
from snapcook_core.schema.graph import Action, LiteralChunk, TextTemplate
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.recipe import Recipe

__all__ = ["Revision", "carry_translations", "revise", "text_for_editing"]

# What the text may set. Visibility is not among them: sharing is a decision
# of its own, not a line someone edits by accident.
_EDITABLE_FRONT = (
    "title",
    "description",
    "servings",
    "prep time",
    "cook time",
    "rest time",
    "total time",
    "lang",
    "tags",
)


@dataclass(frozen=True)
class Revision:
    """The edited recipe, or why the text does not read."""

    recipe: Recipe | None
    problem: str = ""
    detail: str = ""


def text_for_editing(recipe: Recipe) -> str:
    """The recipe as Cooklang in its own language, without what the text cannot set."""
    from snapcook_core.cooklang import print_cook

    front, body = parse_document(print_cook(recipe))
    kept = {key: front[key] for key in _EDITABLE_FRONT if key in front}
    return f"{dump_frontmatter(kept)}\n{body.strip()}\n"


def revise(
    current: Recipe, cooklang: str, *, registry: IngredientRegistry | None = None
) -> Revision:
    """``current`` as the edited text says, kept the same recipe."""
    try:
        front, body = parse_document(cooklang)
        kept = {key: front[key] for key in _EDITABLE_FRONT if key in front}
        text = f"{dump_frontmatter(kept)}\n{tidy_amounts(body).strip()}\n"
        parsed = parse_cook(text, registry=registry)
        recipe = parsed.model_copy(
            update={
                "id": current.id,
                "visibility": current.visibility,
                "provenance": current.provenance,
                "glossary": current.glossary,
            }
        )
        recipe = carry_translations(current, recipe)
    except (SnapcookError, ValueError, ArithmeticError, YAMLError) as error:
        return Revision(None, UNREADABLE, (str(error).strip().splitlines() or [""])[0][:300])
    return Revision(recipe)


def carry_translations(old: Recipe, new: Recipe) -> Recipe:
    """``new`` with every translation ``old`` had for a string that is unchanged.

    Matched by the source string itself, not by position: a step that moved
    keeps its translation, and one whose words changed does not. A translation
    records the hash of its source, so one carried over is exactly as fresh as
    it was.
    """
    known: dict[tuple[str, str], LocalizedText] = {}
    for value in _localized(old):
        known.setdefault((value.source, value.values[value.source]), value)

    def carry(value: LocalizedText) -> LocalizedText:
        source_text = value.values[value.source]
        prior = known.get((value.source, source_text))
        if prior is None:
            return value
        return LocalizedText(
            source=value.source,
            values={**prior.values, value.source: source_text},
            stale_against=dict(prior.stale_against),
        )

    carried = _map_localized(new, carry)
    # model_copy does not validate; a round trip runs every invariant again.
    return Recipe.model_validate(carried.model_dump())


def _localized(recipe: Recipe) -> Iterator[LocalizedText]:
    """Every piece of prose in ``recipe``."""
    found: list[LocalizedText] = []
    _map_localized(recipe, lambda value: found.append(value) or value)
    yield from found


def _map_localized(recipe: Recipe, fn: Callable[[LocalizedText], LocalizedText]) -> Recipe:
    """``recipe`` with ``fn`` applied to every :class:`LocalizedText` in it."""

    def each(value: LocalizedText | None) -> LocalizedText | None:
        return fn(value) if value is not None else None

    def action(item: Action) -> Action:
        text = item.text
        if text is not None:
            text = TextTemplate(
                chunks=[
                    LiteralChunk(text=fn(chunk.text)) if isinstance(chunk, LiteralChunk) else chunk
                    for chunk in text.chunks
                ]
            )
        return item.model_copy(
            update={
                "section": each(item.section),
                "verb": each(item.verb),
                "notes": each(item.notes),
                "text": text,
                "produces": item.produces.model_copy(update={"name": each(item.produces.name)}),
                "timers": [
                    timer.model_copy(update={"name": each(timer.name)}) for timer in item.timers
                ],
                "ingredients": [
                    use.model_copy(update={"prep": each(use.prep), "notes": each(use.notes)})
                    for use in item.ingredients
                ],
                "cookware": [
                    tool.model_copy(update={"name": fn(tool.name), "notes": each(tool.notes)})
                    for tool in item.cookware
                ],
            }
        )

    return recipe.model_copy(
        update={
            "title": fn(recipe.title),
            "description": each(recipe.description),
            "actions": [action(item) for item in recipe.actions],
        }
    )
