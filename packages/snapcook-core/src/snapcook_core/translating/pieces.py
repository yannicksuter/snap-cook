# SPDX-License-Identifier: Apache-2.0
"""The words of a recipe a translation fills in, and filling them in.

A translation changes words, never structure (``RECIPE_SPEC.md`` §7): amounts,
times, temperatures, ingredients and the graph stay as authored. So a translator
never sees them as text. A step goes out as its prose with numbered slots,
``Den ⟦1⟧ mit dem ⟦2⟧ verrühren``, comes back as ``Stir the ⟦1⟧ into the ⟦2⟧``,
and the renderer fills the slots in the reader's language.

Every translated string records the hash of the source it was made from (see
:mod:`snapcook_core.schema.i18n`), so editing one step makes exactly that step's
translation stale, and the next translation redoes only what is stale or
missing. Words no registry knows -- an ingredient it cannot bind, a unit it
cannot resolve -- go to the recipe's ``glossary`` instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from snapcook_core.registry import IngredientRegistry, default_registry
from snapcook_core.schema.graph import (
    Action,
    CookwareChunk,
    IngredientChunk,
    LiteralChunk,
    StateChunk,
    TemperatureChunk,
    TextTemplate,
    TimerChunk,
)
from snapcook_core.schema.i18n import LocalizedText, source_string_hash
from snapcook_core.schema.recipe import Recipe

__all__ = ["Piece", "Translated", "apply_translation", "pending_pieces"]

_SLOT = re.compile(r"⟦(\d+)⟧")


@dataclass(frozen=True)
class Piece:
    """One thing to translate. ``note`` tells the translator what it is."""

    key: str
    text: str
    note: str = ""


@dataclass(frozen=True)
class Translated:
    """A piece as it was sent, and the translation that came back."""

    piece: Piece
    text: str


def pending_pieces(
    recipe: Recipe, lang: str, *, registry: IngredientRegistry | None = None
) -> list[Piece]:
    """What ``recipe`` still needs translated into ``lang``: missing or stale.

    Empty when ``lang`` is the recipe's own language, and once a translation
    has filled everything in.
    """
    if _base(lang) == _base(recipe.source_lang):
        return []
    registry = registry or default_registry()
    pieces: list[Piece] = []

    def localized(key: str, value: LocalizedText | None, note: str) -> None:
        if value is not None and _needs(value, lang):
            pieces.append(Piece(key, value.values[value.source], note))

    localized("title", recipe.title, "the recipe's name")
    localized("description", recipe.description, "one sentence saying what the dish is")
    for action in recipe.actions:
        if action.section is not None and f"section:{_text(action.section)}" not in {
            piece.key for piece in pieces
        }:
            localized(
                f"section:{_text(action.section)}",
                action.section,
                "the name of a part of the recipe, such as the dough or the glaze, "
                "a heading over its ingredients and steps",
            )
        step = _step_piece(action, recipe, lang)
        if step is not None:
            pieces.append(step)
        localized(f"verb:{action.id}", action.verb, "the verb of a step, shown on a diagram")
        localized(f"notes:{action.id}", action.notes, "a note on a step")
        localized(
            f"state:{action.produces.id}",
            action.produces.name,
            "what a step makes, such as a dough or a sauce, named for later steps",
        )
        for index, timer in enumerate(action.timers):
            localized(f"timer:{action.id}:{index}", timer.name, "the name of a timer")
        for use in action.ingredients:
            localized(f"prep:{use.id}", use.prep, "how an ingredient is prepared")
            localized(f"inote:{use.id}", use.notes, "a note on an ingredient")
        for item in action.cookware:
            localized(f"cookware:{item.id}", item.name, "a pan, tin, pot or tool")
            localized(f"cnote:{item.id}", item.notes, "a note on a pan or tool")

    known = recipe.glossary.get(lang, {})
    for word, note in _words(recipe, registry).items():
        if word not in known:
            pieces.append(Piece(f"word:{word}", word, note))
    return pieces


def apply_translation(
    recipe: Recipe,
    lang: str,
    done: Iterable[Translated],
    *,
    registry: IngredientRegistry | None = None,
) -> tuple[Recipe, list[str]]:
    """``recipe`` with the translations filled in, and the keys refused.

    A translation applies only while its piece is still pending with the text
    that was sent: if the recipe changed in the meantime, that piece is left for
    the next translation. A step whose slots came back missing, repeated or out
    of order is refused and keeps its source prose.
    """
    registry = registry or default_registry()
    current = {piece.key: piece for piece in pending_pieces(recipe, lang, registry=registry)}
    accepted = {
        item.piece.key: item.text
        for item in done
        if item.piece.key in current and current[item.piece.key].text == item.piece.text
    }
    refused: list[str] = []

    def localized(key: str, value: LocalizedText | None) -> LocalizedText | None:
        text = accepted.get(key)
        if value is None or text is None:
            return value
        return _with(value, lang, text)

    def action(item: Action) -> Action:
        update: dict[str, object] = {
            "section": (
                localized(f"section:{_text(item.section)}", item.section) if item.section else None
            ),
            "verb": localized(f"verb:{item.id}", item.verb),
            "notes": localized(f"notes:{item.id}", item.notes),
            "produces": item.produces.model_copy(
                update={"name": localized(f"state:{item.produces.id}", item.produces.name)}
            ),
            "timers": [
                timer.model_copy(update={"name": localized(f"timer:{item.id}:{n}", timer.name)})
                for n, timer in enumerate(item.timers)
            ],
            "ingredients": [
                use.model_copy(
                    update={
                        "prep": localized(f"prep:{use.id}", use.prep),
                        "notes": localized(f"inote:{use.id}", use.notes),
                    }
                )
                for use in item.ingredients
            ],
            "cookware": [
                tool.model_copy(
                    update={
                        "name": localized(f"cookware:{tool.id}", tool.name),
                        "notes": localized(f"cnote:{tool.id}", tool.notes),
                    }
                )
                for tool in item.cookware
            ],
        }
        step = accepted.get(f"step:{item.id}")
        if step is not None and item.text is not None:
            template = _with_step(item.text, lang, step, recipe.source_lang)
            if template is None:
                refused.append(f"step:{item.id}")
            else:
                update["text"] = template
        return item.model_copy(update=update)

    words = _words(recipe, registry)
    glossary = dict(recipe.glossary)
    known = {word: text for word, text in glossary.get(lang, {}).items() if word in words}
    for key, text in accepted.items():
        if key.startswith("word:") and text.strip():
            known[key.removeprefix("word:")] = text.strip()
    if known:
        glossary[lang] = known
    else:
        glossary.pop(lang, None)

    translated = recipe.model_copy(
        update={
            "title": localized("title", recipe.title),
            "description": localized("description", recipe.description),
            "actions": [action(item) for item in recipe.actions],
            "glossary": glossary,
        }
    )
    # model_copy does not validate; a round trip runs every invariant again.
    return Recipe.model_validate(translated.model_dump()), refused


def _step_piece(action: Action, recipe: Recipe, lang: str) -> Piece | None:
    if action.text is None:
        return None
    literals = [chunk for chunk in action.text.chunks if isinstance(chunk, LiteralChunk)]
    if not any(_needs(chunk.text, lang) for chunk in literals):
        return None
    parts: list[str] = []
    slots: list[str] = []
    for chunk in action.text.chunks:
        if isinstance(chunk, LiteralChunk):
            parts.append(chunk.text.values[chunk.text.source])
        else:
            slots.append(_slot(chunk, action, recipe))
            parts.append(f"⟦{len(slots)}⟧")
    note = "a step of the method"
    if slots:
        note += "; " + "; ".join(f"⟦{n}⟧ is {what}" for n, what in enumerate(slots, start=1))
    return Piece(f"step:{action.id}", "".join(parts), note)


def _slot(chunk: object, action: Action, recipe: Recipe) -> str:
    if isinstance(chunk, IngredientChunk):
        use = next(use for use in action.ingredients if use.id == chunk.ref)
        return f"the ingredient {use.name!r} with its amount"
    if isinstance(chunk, CookwareChunk):
        tool = next(tool for tool in action.cookware if tool.id == chunk.ref)
        return f"the pan or tool {tool.name.values[tool.name.source]!r}"
    if isinstance(chunk, StateChunk):
        for other in recipe.actions:
            if other.produces.id == chunk.ref and other.produces.name is not None:
                name = other.produces.name
                return f"{name.values[name.source]!r}, made in an earlier step"
        return "what an earlier step made"
    if isinstance(chunk, TimerChunk):
        return "a time"
    if isinstance(chunk, TemperatureChunk):
        return "a temperature, with its oven setting if it has one"
    return "a part of the recipe"


def _with_step(
    template: TextTemplate, lang: str, translation: str, source_lang: str
) -> TextTemplate | None:
    """The template with ``lang`` filled in, or ``None`` if the slots do not fit.

    The words between two slots go to the literal chunk between them. Where the
    source had none -- two slots side by side -- a chunk empty in the source
    language holds the translation's words, which keeps the slot sequence
    intact.
    """
    parts = _SLOT.split(translation)
    gaps, numbers = parts[0::2], [int(n) for n in parts[1::2]]
    slot_count = sum(1 for chunk in template.chunks if not isinstance(chunk, LiteralChunk))
    if numbers != list(range(1, slot_count + 1)):
        return None

    chunks: list[object] = []
    gap = 0
    filled: set[int] = set()
    for chunk in template.chunks:
        if isinstance(chunk, LiteralChunk):
            text = "" if gap in filled else gaps[gap]
            filled.add(gap)
            chunks.append(LiteralChunk(text=_with(chunk.text, lang, text)))
            continue
        if gap not in filled and gaps[gap]:
            chunks.append(LiteralChunk(text=_new_literal(source_lang, lang, gaps[gap])))
        filled.add(gap)
        chunks.append(chunk)
        gap += 1
    if gap not in filled and gaps[gap]:
        chunks.append(LiteralChunk(text=_new_literal(source_lang, lang, gaps[gap])))
    return TextTemplate(chunks=chunks)


def _words(recipe: Recipe, registry: IngredientRegistry) -> dict[str, str]:
    """The words no registry knows, each with a note for the translator."""
    words: dict[str, str] = {}
    for action in recipe.actions:
        for use in action.ingredients:
            if registry.get(use.ingredient_id) is None:
                words.setdefault(use.name, "an ingredient's name, as in a list of ingredients")
            quantity = use.quantity.quantity if use.quantity is not None else None
            unit = getattr(quantity, "unit", None)
            if unit is not None and unit.unit_id is None:
                words.setdefault(unit.surface, "a unit of measure, such as a packet or a tub")
    return words


def _with(value: LocalizedText, lang: str, text: str) -> LocalizedText:
    return LocalizedText(
        source=value.source,
        values={**value.values, lang: text},
        stale_against={
            **value.stale_against,
            lang: source_string_hash(value.values[value.source]),
        },
    )


def _new_literal(source_lang: str, lang: str, text: str) -> LocalizedText:
    return LocalizedText(
        source=source_lang,
        values={source_lang: "", lang: text},
        stale_against={lang: source_string_hash("")},
    )


def _needs(value: LocalizedText, lang: str) -> bool:
    return lang not in value.values or value.is_stale(lang)


def _text(value: LocalizedText) -> str:
    return value.values[value.source]


def _base(lang: str) -> str:
    return lang.split("-", 1)[0].casefold()
