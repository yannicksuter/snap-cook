# SPDX-License-Identifier: Apache-2.0
"""Ergonomic constructors for building recipes in Python.

Assembling a :class:`Recipe` by hand is verbose -- every quantity is a spec
wrapping a discriminated union, every string is localised. These helpers cut the
noise so the corpus (and tests) read like recipes rather than like AST
construction. They are in the shipped package, not the test tree, because the
corpus is a product artifact and a future CLI or seed script wants the same
builders.

A :class:`Chef` is bound to a source language; its ``t`` makes a
:class:`LocalizedText` and its quantity helpers make specs. Nothing here adds
validation the schema does not already enforce -- an invalid graph still raises
at :class:`Recipe` construction.
"""

from __future__ import annotations

from decimal import Decimal

from snapcook_core.ids import UnitId
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

__all__ = ["Chef"]


def _d(value: str | int | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


class Chef:
    """A source-language-bound recipe builder."""

    def __init__(self, source: str) -> None:
        self.source = source

    # -- text -----------------------------------------------------------------

    def t(self, **langs: str) -> LocalizedText:
        return LocalizedText(source=self.source, values=langs)

    # -- quantities -----------------------------------------------------------

    def scalar(
        self,
        value: str | int | Decimal,
        unit_id: str,
        symbol: str,
        policy: ScalingPolicy = ScalingPolicy.LINEAR,
    ) -> QuantitySpec:
        unit = UnitRef(unit_id=UnitId(unit_id), surface=symbol)
        return QuantitySpec(quantity=Scalar(value=_d(value), unit=unit), scaling=policy)

    def range(
        self,
        low: str | int | Decimal,
        high: str | int | Decimal,
        unit_id: str,
        symbol: str,
    ) -> QuantitySpec:
        unit = UnitRef(unit_id=UnitId(unit_id), surface=symbol)
        return QuantitySpec(quantity=Range(low=_d(low), high=_d(high), unit=unit))

    def count(
        self,
        value: str | int | Decimal,
        size: SizeGrade | None = None,
        high: str | int | Decimal | None = None,
    ) -> QuantitySpec:
        return QuantitySpec(
            quantity=Count(value=_d(value), high=None if high is None else _d(high), size=size)
        )

    def approx(self, token: ApproxToken, surface: str) -> QuantitySpec:
        return QuantitySpec(
            quantity=Approx(token=token, surface=surface), scaling=ScalingPolicy.INVARIANT
        )

    # -- elements -------------------------------------------------------------

    def ingredient(
        self,
        use_id: str,
        ingredient_id: str,
        surface: str,
        quantity: QuantitySpec | None = None,
        *,
        optional: bool = False,
        prep: LocalizedText | None = None,
    ) -> IngredientUse:
        return IngredientUse(
            id=use_id,
            name=surface,
            ingredient_id=ingredient_id,
            quantity=quantity,
            optional=optional,
            prep=prep,
        )

    def cookware(self, use_id: str, **langs: str) -> CookwareUse:
        return CookwareUse(id=use_id, name=self.t(**langs))

    def timer(self, quantity: QuantitySpec, name: LocalizedText | None = None) -> Timer:
        return Timer(name=name, quantity=quantity.quantity)  # type: ignore[arg-type]

    def temp(self, value: str | int | Decimal, unit: str = "C") -> Temperature:
        return Temperature(value=_d(value), unit=unit)  # type: ignore[arg-type]

    def state(self, state_id: str, **langs: str) -> FoodState:
        return FoodState(id=state_id, name=self.t(**langs) if langs else None)

    # -- prose chunks ---------------------------------------------------------

    def lit(self, **langs: str) -> LiteralChunk:
        return LiteralChunk(text=self.t(**langs))

    @staticmethod
    def ref(use_id: str) -> IngredientChunk:
        return IngredientChunk(ref=use_id)

    @staticmethod
    def tool(use_id: str) -> CookwareChunk:
        return CookwareChunk(ref=use_id)

    @staticmethod
    def consume(state_id: str) -> StateChunk:
        """A prose reference to a prior food-state -- ``@&{the dough}``."""
        return StateChunk(ref=state_id)

    @staticmethod
    def timer_slot(index: int = 0) -> TimerChunk:
        return TimerChunk(index=index)

    @staticmethod
    def temp_slot(index: int = 0) -> TemperatureChunk:
        return TemperatureChunk(index=index)

    @staticmethod
    def prose(*chunks) -> TextTemplate:
        return TextTemplate(chunks=list(chunks))

    # -- action ---------------------------------------------------------------

    def step(
        self,
        action_id: str,
        produces: FoodState,
        *,
        order: int = 0,
        verb: LocalizedText | None = None,
        uses: list[str] | None = None,
        ingredients: list[IngredientUse] | None = None,
        cookware: list[CookwareUse] | None = None,
        timers: list[Timer] | None = None,
        temperatures: list[Temperature] | None = None,
        text: TextTemplate | None = None,
    ) -> Action:
        return Action(
            id=action_id,
            order=order,
            verb=verb,
            uses=uses or [],
            ingredients=ingredients or [],
            cookware=cookware or [],
            timers=timers or [],
            temperatures=temperatures or [],
            produces=produces,
            text=text,
        )
