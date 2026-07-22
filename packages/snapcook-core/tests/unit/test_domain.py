# SPDX-License-Identifier: Apache-2.0
"""Pure domain accessors and the conversions that succeed.

The property tests hammer the *refusing* paths -- convert without density
raises, cross-dimension raises. This file covers the paths that are supposed to
work: a density that bridges cup-of-flour to grams, a piece weight that turns a
count into a mass, and the small localisation and quantity accessors the
renderers lean on.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snapcook_core.errors import NoCountWeightError, NoDensityError
from snapcook_core.schema.i18n import LocalizedText, source_string_hash
from snapcook_core.schema.ingredient import Ingredient, IngredientUse
from snapcook_core.schema.quantity import (
    ApproxToken,
    Count,
    Range,
    Scalar,
    ScalingPolicy,
    SizeGrade,
    UnitRef,
    approx_spec,
)
from snapcook_core.units.density import convert_value, count_to_mass_g, resolve_density_g_per_ml

D = Decimal


# -- i18n ---------------------------------------------------------------------


def test_localized_text_resolve_fallback_chain() -> None:
    text = LocalizedText(source="de", values={"de": "Mehl", "en": "flour"})
    assert text.resolve("de") == ("Mehl", False)
    assert text.resolve("en") == ("flour", False)
    # exact miss -> bare language
    assert text.resolve("en-US") == ("flour", True)
    # miss entirely -> source fallback, flagged
    assert text.resolve("fr", source="de") == ("Mehl", True)


def test_localized_text_requires_source_in_values() -> None:
    with pytest.raises(ValueError, match="source language"):
        LocalizedText(source="de", values={"en": "flour"})


def test_localized_text_staleness_is_per_string() -> None:
    source_hash = source_string_hash("Mehl")
    text = LocalizedText(
        source="de", values={"de": "Mehl", "en": "flour"}, stale_against={"en": source_hash}
    )
    assert text.is_stale("en") is False
    # a language with no recorded source hash is never stale
    assert text.is_stale("fr") is False

    moved = text.model_copy(update={"values": {"de": "Weizenmehl", "en": "flour"}})
    assert moved.is_stale("en") is True  # source changed, translation did not


def test_source_string_hash_is_nfc_stable() -> None:
    assert source_string_hash("café") == source_string_hash("café")


# -- ingredient ---------------------------------------------------------------


def test_ingredient_name_for_falls_back() -> None:
    flour = Ingredient(id="ing_flour", names={"en": "flour", "de": "Mehl"})
    assert flour.name_for("de") == "Mehl"
    assert flour.name_for("en-GB") == "flour"  # bare language
    assert flour.name_for("fr", source="de") == "Mehl"  # source fallback
    assert Ingredient(id="ing_x", names={}).name_for("en") is None


def test_ingredient_piece_weight_defaults_to_medium() -> None:
    onion = Ingredient(id="ing_onion", names={"en": "onion"}, piece_weights_g={"medium": D("150")})
    assert onion.piece_weight(SizeGrade.MEDIUM) == D("150")
    assert onion.piece_weight(None) == D("150")  # None means medium
    assert onion.piece_weight(SizeGrade.LARGE) is None


def test_ingredient_use_bound_flag() -> None:
    assert IngredientUse(id="iuse_1", name="flour", ingredient_id="ing_flour").bound is True
    assert IngredientUse(id="iuse_2", name="mystery").bound is False


# -- quantities ---------------------------------------------------------------


def test_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="exceeds high"):
        Range(low=D("5"), high=D("2"))


def test_count_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="exceeds high"):
        Count(value=D("5"), high=D("2"))
    assert Count(value=D("2"), high=D("4")).is_range is True
    assert Count(value=D("2")).is_range is False


def test_unit_ref_resolved_property() -> None:
    assert UnitRef(unit_id="unit:g", surface="g").resolved is True
    assert UnitRef(unit_id=None, surface="smidgen").resolved is False


def test_approx_cannot_scale_linearly() -> None:
    from snapcook_core.schema.quantity import Approx, QuantitySpec

    with pytest.raises(ValueError, match="LINEAR"):
        QuantitySpec(
            quantity=Approx(token=ApproxToken.PINCH, surface="a pinch"),
            scaling=ScalingPolicy.LINEAR,
        )
    # the helper picks the only sane policy
    spec = approx_spec(ApproxToken.TO_TASTE, "to taste")
    assert spec.scaling is ScalingPolicy.INVARIANT


# -- density conversions that succeed -----------------------------------------


def _flour() -> Ingredient:
    return Ingredient(id="ing_flour", names={"en": "flour"}, density_g_per_ml=D("0.53"))


def test_volume_to_mass_uses_density() -> None:
    grams = convert_value(D("1"), "unit:cup.us", "unit:g", ingredient=_flour())
    # 236.588 ml * 0.53 g/ml
    assert grams == pytest.approx(Decimal("125.39"), abs=Decimal("0.01"))


def test_mass_to_volume_uses_density_inverse() -> None:
    millilitres = convert_value(D("125.39164"), "unit:g", "unit:ml", ingredient=_flour())
    assert millilitres == pytest.approx(Decimal("236.588"), abs=Decimal("0.01"))


def test_resolve_density_threads_prep_state() -> None:
    assert resolve_density_g_per_ml(None) is None
    assert resolve_density_g_per_ml(_flour(), prep_state="sifted") == D("0.53")


def test_same_dimension_conversion_needs_no_ingredient() -> None:
    assert convert_value(D("500"), "unit:g", "unit:kg") == Decimal("0.5")


def test_count_to_mass_success_and_refusal() -> None:
    onion = Ingredient(id="ing_onion", names={"en": "onion"}, piece_weights_g={"medium": D("150")})
    assert count_to_mass_g(D("2"), onion, SizeGrade.MEDIUM) == D("300")
    with pytest.raises(NoCountWeightError):
        count_to_mass_g(D("2"), onion, SizeGrade.LARGE)
    with pytest.raises(NoCountWeightError):
        count_to_mass_g(D("1"), None)


def test_volume_to_mass_without_density_still_refuses() -> None:
    water = Ingredient(id="ing_x", names={"en": "x"})
    with pytest.raises(NoDensityError):
        convert_value(D("1"), "unit:cup.us", "unit:g", ingredient=water)
