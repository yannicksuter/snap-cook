# SPDX-License-Identifier: Apache-2.0
"""Turn a model's reading of a source into a draft a person can check.

Pure and total: whatever a model returns, these functions return a
:class:`Draft` and never raise. A model that writes a cyclic graph, a fraction
the parser cannot read, or no recipe at all produces a draft with a problem the
reader can see and fix, not a failed job.

The draft is Cooklang text plus the recipe parsed from it. The text stays the
single source of truth while a person reviews it: answering a question edits
the text, changing the title edits its frontmatter, and every change parses
again through :func:`read_draft`. Only saving commits the parsed recipe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from ruamel.yaml import YAMLError

from snapcook_core.cooklang import parse_cook
from snapcook_core.cooklang.frontmatter import dump_frontmatter, parse_document
from snapcook_core.errors import SnapcookError
from snapcook_core.importing.contracts import Answer, CupSize, ImportSource, RawExtraction
from snapcook_core.schema.provenance import Provenance
from snapcook_core.schema.recipe import Recipe
from snapcook_core.units.registry import resolve_unit

__all__ = [
    "NOT_A_RECIPE",
    "UNREADABLE",
    "Draft",
    "apply_answer",
    "normalize",
    "read_draft",
    "tidy_amounts",
    "with_details",
]

NOT_A_RECIPE = "not_a_recipe"
UNREADABLE = "unreadable"

_FRACTIONS = {
    "½": "0.5", "⅓": "0.33", "⅔": "0.67", "¼": "0.25", "¾": "0.75",
    "⅕": "0.2", "⅖": "0.4", "⅗": "0.6", "⅘": "0.8", "⅙": "0.17", "⅚": "0.83",
    "⅛": "0.125", "⅜": "0.375", "⅝": "0.625", "⅞": "0.875",
}  # fmt: skip
# The braced body of an ingredient or timer token: @name{body}, ~{body}.
_TOKEN_BODY = re.compile(r"(?P<head>@(?!&)[?=]*[^@#~^{}\n]*|~[^@#~^{}\n]*)\{(?P<body>[^{}\n]*)\}")
_MIXED = re.compile(r"^(?P<whole>\d+)\s+(?P<num>\d+)\s*/\s*(?P<den>\d+)$")
_SIMPLE = re.compile(r"^(?P<num>\d+)\s*/\s*(?P<den>\d+)$")
_DECIMAL_COMMA = re.compile(r"^(?P<int>\d+),(?P<dec>\d+)$")
_LEADING_INT = re.compile(r"\d+")
_PRODUCED = re.compile(r"=>\s*(?P<name>[^\n{}@#~^]+?)\s*$", re.MULTILINE)
_REFERENCE = re.compile(r"@&\{(?P<name>[^{}]*)\}")
_CUPS = ("cup", "cups")
# What the model may set in frontmatter. Visibility and attribution are not the
# model's to decide: imports land private, and provenance comes from the import.
_FRONT_KEYS = ("title", "description", "servings", "lang", "tags")


@dataclass(frozen=True)
class Draft:
    """A reading of a source: the text, and the recipe if the text holds one."""

    cooklang: str
    recipe: Recipe | None = None
    problem: str | None = None
    """``NOT_A_RECIPE`` or ``UNREADABLE`` when there is no recipe to save."""
    detail: str = ""
    unknown_references: tuple[str, ...] = ()
    """Intermediates a step uses (``@&{name}``) that no step makes. The text
    still parses -- the reference reads as plain words -- but the structure the
    source described is lost, so a reviewer should know."""


def normalize(raw: RawExtraction, source: ImportSource) -> Draft:
    """The first draft of an import: the model's text, attributed to its source."""
    if not raw.is_recipe or not raw.cooklang.strip():
        return Draft(cooklang=raw.cooklang, problem=NOT_A_RECIPE)
    provenance = Provenance(
        origin="imported",
        source_url=source.url,
        source_title=raw.source_title,
        author=raw.source_author,
    )
    return read_draft(raw.cooklang, cups=raw.cups, provenance=provenance)


def read_draft(
    cooklang: str, *, cups: CupSize | None = None, provenance: Provenance | None = None
) -> Draft:
    """Parse draft text into a private recipe, or say why it does not parse."""
    try:
        front, body = parse_document(cooklang)
    except YAMLError as error:
        return Draft(cooklang=cooklang, problem=UNREADABLE, detail=_first_line(error))

    text = f"{dump_frontmatter(_tidy_front(front))}\n{tidy_amounts(body).strip()}\n"
    try:
        recipe = parse_cook(text)
        recipe = _finish(recipe, cups, provenance or Provenance(origin="imported"))
    except (SnapcookError, ValueError, ArithmeticError, YAMLError) as error:
        return Draft(cooklang=text, problem=UNREADABLE, detail=_first_line(error))
    return Draft(cooklang=text, recipe=recipe, unknown_references=_unknown_references(body))


def apply_answer(cooklang: str, answer: Answer) -> str | None:
    """The text with one answer's edit made, or ``None`` if it no longer applies."""
    if not answer.find or answer.find not in cooklang:
        return None
    return cooklang.replace(answer.find, answer.replace, 1)


def with_details(cooklang: str, *, title: str, description: str, servings: int | None) -> str:
    """The text with new frontmatter values, the steps untouched."""
    try:
        front, body = parse_document(cooklang)
    except YAMLError:
        front, body = {}, cooklang
    front["title"] = title.strip() or front.get("title") or "Untitled"
    if description.strip():
        front["description"] = description.strip()
    else:
        front.pop("description", None)
    if servings:
        front["servings"] = servings
    else:
        front.pop("servings", None)
    return f"{dump_frontmatter(_tidy_front(front))}\n{body.strip()}\n"


def tidy_amounts(text: str) -> str:
    """Rewrite amounts the parser cannot read into ones it can.

    Models and cookbooks write ``½``, ``1 1/2`` and ``1,5``; the parser reads
    decimals with a point. Only the number in front of a unit changes, so an
    approximation such as ``{nach Geschmack}`` is left alone.
    """

    def tidy(match: re.Match[str]) -> str:
        number, sep, unit = match.group("body").partition("%")
        return f"{match.group('head')}{{{_decimal(number.strip())}{sep}{unit}}}"

    return _TOKEN_BODY.sub(tidy, text)


def _decimal(number: str) -> str:
    for glyph, value in _FRACTIONS.items():
        if glyph in number:
            whole = number.replace(glyph, "").strip()
            if not whole:
                return value
            if whole.isdigit():
                return str(Decimal(whole) + Decimal(value))
            return number
    if match := _MIXED.match(number):
        return _quotient(int(match["whole"]), int(match["num"]), int(match["den"]), number)
    if match := _SIMPLE.match(number):
        return _quotient(0, int(match["num"]), int(match["den"]), number)
    if match := _DECIMAL_COMMA.match(number):
        return f"{match['int']}.{match['dec']}"
    return number


def _quotient(whole: int, numerator: int, denominator: int, original: str) -> str:
    if denominator == 0:
        return original
    try:
        value = Decimal(whole) + Decimal(numerator) / Decimal(denominator)
    except InvalidOperation:
        return original
    return format(value.quantize(Decimal("0.001")).normalize(), "f")


def _tidy_front(front: dict[str, Any]) -> dict[str, Any]:
    tidy: dict[str, Any] = {}
    title = str(front.get("title") or "").strip()
    tidy["title"] = title or "Untitled"
    description = str(front.get("description") or "").strip()
    if description:
        tidy["description"] = description
    servings = front.get("servings")
    if isinstance(servings, str):
        match = _LEADING_INT.search(servings)
        servings = int(match.group()) if match else None
    if isinstance(servings, int) and not isinstance(servings, bool) and servings > 0:
        tidy["servings"] = servings
    lang = str(front.get("lang") or "en").strip().lower()[:2]
    tidy["lang"] = lang if lang.isalpha() else "en"
    tags = front.get("tags")
    if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
        tidy["tags"] = [tag.strip() for tag in tags if tag.strip()]
    return {key: tidy[key] for key in _FRONT_KEYS if key in tidy}


def _finish(recipe: Recipe, cups: CupSize | None, provenance: Provenance) -> Recipe:
    data = recipe.model_dump()
    data["visibility"] = "private"
    data["provenance"] = provenance.model_dump()
    if cups is not None:
        _resolve_cups(data, resolve_unit("cup", locale=cups))
    return Recipe.model_validate(data)


def _resolve_cups(node: Any, unit_id: str | None) -> None:
    """Give every unresolved "cup" the cup the source means.

    A bare cup is 200 to 284 ml depending on the country, so the parser leaves
    it unresolved. The model saw the source and says which; resolution happens
    here, at authoring time, and is frozen into the version.
    """
    if isinstance(node, dict):
        if (
            node.keys() >= {"unit_id", "surface"}
            and node["unit_id"] is None
            and str(node["surface"]).strip().lower() in _CUPS
        ):
            node["unit_id"] = unit_id
        for value in node.values():
            _resolve_cups(value, unit_id)
    elif isinstance(node, list):
        for value in node:
            _resolve_cups(value, unit_id)


def _unknown_references(body: str) -> tuple[str, ...]:
    produced = {match["name"].strip() for match in _PRODUCED.finditer(body)}
    used = {match["name"].strip() for match in _REFERENCE.finditer(body)}
    return tuple(sorted(used - produced))


def _first_line(error: Exception) -> str:
    return (str(error).strip().splitlines() or [type(error).__name__])[0][:300]
