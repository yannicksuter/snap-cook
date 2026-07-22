# SPDX-License-Identifier: Apache-2.0
"""Parse Cooklang-flavoured text into a recipe.

The input half of the authoring format. It reads the canonical form the printer
emits -- brace-delimited tokens, explicit ``@&{state}`` consumption, one step per
paragraph -- and lowers it to a validated :class:`Recipe`. Because construction
runs the graph validators, a document describing a cyclic or dangling graph
fails here rather than producing a broken recipe.

The parser is intentionally scoped to snap-cook's canonical dialect, not the full
breadth of hand-written Cooklang. It is the inverse of the printer, and the round
trip ``print(parse(T)) == T`` is the gate that keeps them honest. Ingredient
names are bound to the registry where possible; an unbound name is kept verbatim
and flagged, never dropped.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from snapcook_core import ids
from snapcook_core.cooklang.frontmatter import parse_document
from snapcook_core.registry import IngredientRegistry, default_registry
from snapcook_core.schema.cookware import CookwareUse
from snapcook_core.schema.graph import (
    Action,
    CookwareChunk,
    FoodState,
    IngredientChunk,
    LiteralChunk,
    StateChunk,
    Temperature,
    TemperatureChunk,
    TextTemplate,
    Timer,
    TimerChunk,
)
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.ingredient import IngredientUse
from snapcook_core.schema.provenance import Provenance
from snapcook_core.schema.quantity import (
    Approx,
    ApproxToken,
    Count,
    QuantitySpec,
    Range,
    Scalar,
    ScalingPolicy,
    SizeGrade,
    UnitRef,
)
from snapcook_core.schema.recipe import Recipe
from snapcook_core.units.registry import resolve_unit

__all__ = ["parse_cook"]

_SIZE_VALUES = {grade.value for grade in SizeGrade}
_PRODUCE = re.compile(r"\s*=>\s*(?P<name>[^{}@#~^]+?)\s*$")

# Surface -> approx token, best effort. Text round-trips on the surface alone, so
# an unrecognised phrase is stored as AS_NEEDED without affecting the printed form.
_APPROX_TOKENS: dict[str, ApproxToken] = {
    "a pinch": ApproxToken.PINCH,
    "eine prise": ApproxToken.PINCH,
    "a dash": ApproxToken.DASH,
    "ein spritzer": ApproxToken.DASH,
    "a splash": ApproxToken.SPLASH,
    "ein schuss": ApproxToken.SPLASH,
    "a handful": ApproxToken.HANDFUL,
    "eine handvoll": ApproxToken.HANDFUL,
    "a knob": ApproxToken.KNOB,
    "ein stück": ApproxToken.KNOB,
    "to taste": ApproxToken.TO_TASTE,
    "nach geschmack": ApproxToken.TO_TASTE,
    "as needed": ApproxToken.AS_NEEDED,
    "nach bedarf": ApproxToken.AS_NEEDED,
    "for garnish": ApproxToken.FOR_GARNISH,
    "zum garnieren": ApproxToken.FOR_GARNISH,
    "for frying": ApproxToken.FOR_FRYING,
    "zum braten": ApproxToken.FOR_FRYING,
    "to cover": ApproxToken.TO_COVER,
    "zum bedecken": ApproxToken.TO_COVER,
}


def parse_cook(text: str, *, registry: IngredientRegistry | None = None) -> Recipe:
    """Parse a Cooklang document into a validated recipe."""
    registry = registry or default_registry()
    front, body = parse_document(text)
    lang = front.get("lang", "en")

    name_to_state: dict[str, str] = {}
    actions: list[Action] = []
    for index, block in enumerate(_split_steps(body), start=1):
        actions.append(_parse_step(block, index, lang, registry, name_to_state))

    return Recipe(
        id=ids.new_recipe_id(),
        source_lang=lang,
        title=LocalizedText.mono(lang, front.get("title", "Untitled")),
        description=(
            LocalizedText.mono(lang, front["description"]) if front.get("description") else None
        ),
        servings=front.get("servings"),
        visibility=front.get("visibility", "private"),
        tags=list(front.get("tags", []) or []),
        provenance=Provenance(
            source_url=front.get("source_url"),
            license_spdx=front.get("license"),
            author=front.get("author"),
        ),
        actions=actions,
    )


def _split_steps(body: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]


def _parse_step(
    block: str,
    index: int,
    lang: str,
    registry: IngredientRegistry,
    name_to_state: dict[str, str],
) -> Action:
    text = block.replace("\n", " ")

    produced_name: str | None = None
    match = _PRODUCE.search(text)
    if match:
        produced_name = match.group("name").strip()
        text = text[: match.start()]

    parser = _StepScanner(text, index, lang, registry, name_to_state)
    parser.run()

    action_id = f"act_{index}"
    if produced_name:
        state_id = f"nod_{index}_{_slug(produced_name)}"
        produces = FoodState(id=state_id, name=LocalizedText.mono(lang, produced_name))
        name_to_state[produced_name] = state_id
    else:
        produces = FoodState(id=f"nod_{index}", name=None)

    template = TextTemplate(chunks=parser.chunks) if parser.chunks else None

    return Action(
        id=action_id,
        order=index - 1,
        uses=parser.uses,
        ingredients=parser.ingredients,
        cookware=parser.cookware,
        timers=parser.timers,
        temperatures=parser.temperatures,
        produces=produces,
        text=template,
    )


class _StepScanner:
    """Left-to-right scan of one step's prose into chunks and structured parts."""

    def __init__(self, text, index, lang, registry, name_to_state) -> None:
        self.text = text
        self.index = index
        self.lang = lang
        self.registry = registry
        self.name_to_state = name_to_state

        self.chunks: list = []
        self.ingredients: list[IngredientUse] = []
        self.cookware: list[CookwareUse] = []
        self.timers: list[Timer] = []
        self.temperatures: list[Temperature] = []
        self.uses: list[str] = []
        self._counter = 0

    def _next(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self.index}_{self._counter}"

    def run(self) -> None:
        literal = ""
        i = 0
        while i < len(self.text):
            ch = self.text[i]
            if ch in "@#~^" and (marker := self._try_token(i)) is not None:
                if literal:
                    self.chunks.append(LiteralChunk(text=LocalizedText.mono(self.lang, literal)))
                    literal = ""
                chunk, i = marker
                self.chunks.append(chunk)
            else:
                literal += ch
                i += 1
        if literal:
            self.chunks.append(LiteralChunk(text=LocalizedText.mono(self.lang, literal)))

    def _try_token(self, i: int):
        ch = self.text[i]
        if ch == "@" and self.text[i + 1 : i + 3] == "&{":
            return self._state(i)
        if ch == "@":
            return self._ingredient(i)
        if ch == "#":
            return self._cookware(i)
        if ch == "~":
            return self._timer(i)
        if ch == "^":
            return self._temperature(i)
        return None

    def _braced(self, start: int) -> tuple[str, int] | None:
        """Body between the first ``{`` at/after ``start`` and its ``}``."""
        open_brace = self.text.find("{", start)
        if open_brace == -1:
            return None
        close = self.text.find("}", open_brace)
        if close == -1:
            return None
        return self.text[open_brace + 1 : close], close + 1

    def _state(self, i: int):
        braced = self._braced(i)
        if braced is None:
            return None
        name, end = braced
        state_id = self.name_to_state.get(name.strip())
        if state_id is None:
            return None  # a forward/unknown reference is not a token here
        if state_id not in self.uses:
            self.uses.append(state_id)
        return StateChunk(ref=state_id), end

    def _ingredient(self, i: int):
        k = i + 1
        mods = ""
        while k < len(self.text) and self.text[k] in "?=":
            mods += self.text[k]
            k += 1
        open_brace = self.text.find("{", k)
        if open_brace == -1:
            return None
        name = self.text[k:open_brace]
        braced = self._braced(open_brace)
        if braced is None:
            return None
        body, end = braced

        use_id = self._next("iuse")
        quantity = _parse_quantity(body, invariant="=" in mods)
        self.ingredients.append(
            IngredientUse(
                id=use_id,
                name=name,
                ingredient_id=self.registry.resolve_name(name, self.lang),
                quantity=quantity,
                optional="?" in mods,
            )
        )
        return IngredientChunk(ref=use_id), end

    def _cookware(self, i: int):
        open_brace = self.text.find("{", i + 1)
        if open_brace == -1:
            return None
        name = self.text[i + 1 : open_brace]
        braced = self._braced(open_brace)
        if braced is None:
            return None
        body, end = braced
        use_id = self._next("cwu")
        quantity = Decimal(body) if body.strip() else None
        self.cookware.append(
            CookwareUse(id=use_id, name=LocalizedText.mono(self.lang, name), quantity=quantity)
        )
        return CookwareChunk(ref=use_id), end

    def _timer(self, i: int):
        open_brace = self.text.find("{", i + 1)
        if open_brace == -1:
            return None
        name = self.text[i + 1 : open_brace]
        braced = self._braced(open_brace)
        if braced is None:
            return None
        body, end = braced
        spec = _parse_quantity(body, invariant=False)
        quantity = spec.quantity if spec is not None else Scalar(value=Decimal(0))
        timer_name = LocalizedText.mono(self.lang, name) if name else None
        index = len(self.timers)
        self.timers.append(Timer(name=timer_name, quantity=quantity))
        return TimerChunk(index=index), end

    def _temperature(self, i: int):
        braced = self._braced(i)
        if braced is None:
            return None
        body, end = braced
        value_str, _, unit = body.partition("%")
        temp = Temperature(value=Decimal(value_str), unit=(unit or "C"))
        index = len(self.temperatures)
        self.temperatures.append(temp)
        return TemperatureChunk(index=index), end


def _parse_quantity(body: str, *, invariant: bool) -> QuantitySpec | None:
    body = body.strip()
    if not body:
        return None

    number_part, sep, unit_part = body.partition("%")
    number_part = number_part.strip()
    unit_part = unit_part.strip()

    if sep and unit_part in _SIZE_VALUES:
        return QuantitySpec(quantity=Count(value=Decimal(number_part), size=SizeGrade(unit_part)))

    if sep:  # a real unit
        unit = UnitRef(unit_id=resolve_unit(unit_part), surface=unit_part)
        if "-" in number_part:
            low, high = number_part.split("-", 1)
            quantity = Range(low=Decimal(low), high=Decimal(high), unit=unit)
        else:
            quantity = Scalar(value=Decimal(number_part), unit=unit)
        scaling = ScalingPolicy.INVARIANT if invariant else ScalingPolicy.LINEAR
        return QuantitySpec(quantity=quantity, scaling=scaling)

    # No unit: a bare count, a counted range, or an approximation.
    if "-" in number_part and _is_number(number_part.split("-", 1)[0]):
        low, high = number_part.split("-", 1)
        return QuantitySpec(quantity=Count(value=Decimal(low), high=Decimal(high)))
    if _is_number(number_part):
        scaling = ScalingPolicy.INVARIANT if invariant else ScalingPolicy.LINEAR
        return QuantitySpec(quantity=Count(value=Decimal(number_part)), scaling=scaling)

    token = _APPROX_TOKENS.get(body.lower(), ApproxToken.AS_NEEDED)
    return QuantitySpec(quantity=Approx(token=token, surface=body), scaling=ScalingPolicy.INVARIANT)


def _is_number(text: str) -> bool:
    try:
        Decimal(text.strip())
    except (InvalidOperation, ValueError):
        return False
    return True


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "state"
