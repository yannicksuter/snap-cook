# SPDX-License-Identifier: Apache-2.0
"""Ingredients: the registry entity and its use inside a recipe.

Two distinct things share the word "ingredient" and conflating them is a classic
recipe-app mistake:

:class:`Ingredient`
    A registry *entity* -- "wheat flour" -- with names in every language, a
    density, a divisibility flag and piece weights. There is one of these per
    real-world ingredient, shared across every recipe that uses it. This is what
    makes "flour" and "Mehl" resolve to a single thing, and what carries the
    density that volume->mass conversion needs.

:class:`IngredientUse`
    One *appearance* of an ingredient in one recipe -- "500 g of flour, sifted".
    It binds to a registry entity by ``ingredient_id`` and adds the quantity,
    the optional flag and the prep note that are specific to this recipe.

The binding can be absent. An importer that cannot match "type 550 flour" to the
registry still stores the use with ``ingredient_id=None`` and the surface name;
that is a warning, not a refusal, because dropping unrecognised ingredients
would make the importer useless on real input. An unbound use simply cannot be
translated or converted -- it renders as authored.
"""

from __future__ import annotations

from decimal import Decimal

from snapcook_core.ids import IngredientId, IngredientUseId
from snapcook_core.schema.base import SnapcookModel
from snapcook_core.schema.i18n import LocalizedText
from snapcook_core.schema.quantity import QuantitySpec, SizeGrade

__all__ = ["Ingredient", "IngredientUse"]


class Ingredient(SnapcookModel):
    """A registry entity, shared across recipes.

    Not part of any single recipe's content hash -- a recipe references it by
    ``id``. The full registry with per-attribute provenance lands in M5; the M1
    subset carries only what rendering the corpus needs.
    """

    id: IngredientId
    names: dict[str, str]
    """Display name per BCP-47 language tag. The join key for translation:
    a recipe stores the id, and the reader's language selects the name here."""

    density_g_per_ml: Decimal | None = None
    """Grams per millilitre, for volume<->mass conversion. ``None`` means the
    conversion must *raise* rather than guess -- a wrong density is invisible
    and worse than a refusal (see :mod:`snapcook_core.units.density`)."""

    divisible: bool = True
    """Whether a fractional amount is meaningful. Eggs are not divisible;
    rounding must not print "1.5 eggs". Flour is; "1.5 cups" is fine."""

    piece_weights_g: dict[str, Decimal] = {}
    """Grams for a counted piece, keyed by :class:`SizeGrade` value. A medium
    onion is ~150 g. Separate data from density, needed to turn "1 onion" into a
    mass."""

    fdc_id: int | None = None
    """USDA FoodData Central id, the join key for nutrition. Reserved for M5."""

    def name_for(self, lang: str, *, source: str | None = None) -> str | None:
        """Registry name in ``lang``, falling back to the bare language then to
        any available name. ``None`` only if the registry entry has no names."""
        if lang in self.names:
            return self.names[lang]
        base = lang.split("-", 1)[0]
        if base in self.names:
            return self.names[base]
        if source and source in self.names:
            return self.names[source]
        return next(iter(self.names.values()), None)

    def piece_weight(self, size: SizeGrade | None) -> Decimal | None:
        """Grams for one piece of the given size grade, if known."""
        key = (size or SizeGrade.MEDIUM).value
        return self.piece_weights_g.get(key)


class IngredientUse(SnapcookModel):
    """One appearance of an ingredient in a recipe.

    ``id`` is stable across edits so the diff can report "the flour changed from
    500 g to 550 g" as a modification of one element rather than a delete plus an
    add.
    """

    id: IngredientUseId
    name: str
    """The surface name as authored, e.g. "flour". Retained even when bound, so
    a recipe can be reprinted as written and an unresolved binding stays
    visible instead of silently vanishing."""

    ingredient_id: IngredientId | None = None
    quantity: QuantitySpec | None = None
    optional: bool = False
    prep: LocalizedText | None = None
    """Preparation state -- "sifted", "finely diced". Localised prose, and also
    the ``prep_state`` that disambiguates density (sifted vs scooped flour)."""

    notes: LocalizedText | None = None

    @property
    def bound(self) -> bool:
        return self.ingredient_id is not None
