# SPDX-License-Identifier: Apache-2.0
"""The ingredient registry: the entity a recipe's ingredient use binds to.

A recipe stores an ``ingredient_id``; the registry turns that id into a name in
the reader's language, a density for volume<->mass, a divisibility flag for
rounding and piece weights for counts. This is what makes "flour" and "Mehl" one
entity rather than two strings to keep in sync.

M1 ships a **curated subset** -- the ingredients the corpus needs, with names in
English and German -- not a full import. ADR 0005 and the roadmap are explicit
that full USDA/FAO ingestion is a later data pipeline, and that seeding it early
risks bending the schema toward whatever those datasets happen to contain. The
data lives inline here rather than in a file so M1 has no packaging or path
concerns; growing past a few hundred entries is the cue to move it to
``seeds/``.

Densities are approximate cooking values (g/ml) and piece weights are typical
medium sizes. They are good enough to render, and precise enough that a US
reader gets a plausible ounce count -- not nutrition-grade data, which is what
the provenance-tracked registry in M5 is for.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from snapcook_core.ids import IngredientId
from snapcook_core.schema.ingredient import Ingredient

__all__ = ["IngredientRegistry", "default_registry"]

# id, names{lang:name}, density_g_per_ml, divisible, piece_weights{grade:g}, fdc_id
_CURATED: tuple[tuple, ...] = (
    ("ing_water", {"en": "water", "de": "Wasser"}, "1.0", True, {}, None),
    ("ing_milk", {"en": "milk", "de": "Milch"}, "1.03", True, {}, None),
    ("ing_flour", {"en": "flour", "de": "Mehl"}, "0.53", True, {}, 169761),
    ("ing_sugar", {"en": "sugar", "de": "Zucker"}, "0.85", True, {}, None),
    ("ing_salt", {"en": "salt", "de": "Salz"}, "1.2", True, {}, None),
    ("ing_pepper", {"en": "pepper", "de": "Pfeffer"}, "0.5", True, {}, None),
    ("ing_butter", {"en": "butter", "de": "Butter"}, "0.911", True, {}, None),
    ("ing_oil", {"en": "vegetable oil", "de": "Pflanzenöl"}, "0.92", True, {}, None),
    ("ing_olive_oil", {"en": "olive oil", "de": "Olivenöl"}, "0.913", True, {}, None),
    (
        "ing_egg",
        {"en": "egg", "de": "Ei"},
        None,
        False,
        {"small": "44", "medium": "50", "large": "63"},
        None,
    ),
    (
        "ing_potato",
        {"en": "potato", "de": "Kartoffel"},
        None,
        True,
        {"small": "120", "medium": "170", "large": "300"},
        None,
    ),
    (
        "ing_onion",
        {"en": "onion", "de": "Zwiebel"},
        None,
        True,
        {"small": "90", "medium": "150", "large": "250"},
        None,
    ),
    (
        "ing_garlic",
        {"en": "garlic", "de": "Knoblauch"},
        None,
        True,
        {"medium": "5"},
        None,
    ),
    ("ing_nutmeg", {"en": "nutmeg", "de": "Muskatnuss"}, "0.5", True, {}, None),
    ("ing_yeast", {"en": "yeast", "de": "Hefe"}, "0.75", True, {}, None),
    (
        "ing_tomato",
        {"en": "tomato", "de": "Tomate"},
        None,
        True,
        {"medium": "120", "large": "180"},
        None,
    ),
    ("ing_cheese", {"en": "cheese", "de": "Käse"}, "0.6", True, {}, None),
    ("ing_bacon", {"en": "bacon", "de": "Speck"}, None, True, {}, None),
    ("ing_parsley", {"en": "parsley", "de": "Petersilie"}, None, True, {}, None),
    ("ing_rosemary", {"en": "rosemary", "de": "Rosmarin"}, None, True, {}, None),
)


class IngredientRegistry:
    """A lookup over curated ingredients, by id and by surface name."""

    def __init__(self, ingredients: dict[IngredientId, Ingredient]) -> None:
        self._by_id = ingredients
        # (lang, lowered name) -> id, for binding an authored surface to an entity.
        self._by_name: dict[tuple[str, str], IngredientId] = {}
        for ing in ingredients.values():
            for lang, name in ing.names.items():
                self._by_name.setdefault((lang, name.lower()), ing.id)

    def get(self, ingredient_id: str | None) -> Ingredient | None:
        if ingredient_id is None:
            return None
        return self._by_id.get(IngredientId(ingredient_id))

    def resolve_name(self, surface: str, lang: str | None = None) -> IngredientId | None:
        """Bind an author-written name to an entity id, or ``None``.

        Tries the given language first, then every language, so a German recipe
        that writes an English ingredient name still binds. A recipe writes
        plurals ("eggs", "Kartoffeln") but the registry stores the singular, so a
        few common plural endings are stripped before giving up. This is a
        heuristic, not a lemmatiser -- unbound is a warning, not a failure, and
        the surface is kept intact either way.
        """
        for candidate in _singular_candidates(surface):
            if lang and (lang, candidate) in self._by_name:
                return self._by_name[(lang, candidate)]
            for (_lang, name), ing_id in self._by_name.items():
                if name == candidate:
                    return ing_id
        return None

    def __contains__(self, ingredient_id: str) -> bool:
        return IngredientId(ingredient_id) in self._by_id


# English and German plural endings, longest first so "-es" is tried before "-s".
_PLURAL_ENDINGS = ("es", "en", "n", "s")


def _singular_candidates(surface: str) -> list[str]:
    """The surface itself, then plausible singular forms of it."""
    key = surface.strip().lower()
    candidates = [key]
    for ending in _PLURAL_ENDINGS:
        if key.endswith(ending) and len(key) > len(ending) + 1:
            candidates.append(key[: -len(ending)])
    return candidates


def _build(raw: tuple[tuple, ...]) -> dict[IngredientId, Ingredient]:
    out: dict[IngredientId, Ingredient] = {}
    for id_, names, density, divisible, piece_weights, fdc_id in raw:
        out[IngredientId(id_)] = Ingredient(
            id=IngredientId(id_),
            names=names,
            density_g_per_ml=Decimal(density) if density is not None else None,
            divisible=divisible,
            piece_weights_g={k: Decimal(v) for k, v in piece_weights.items()},
            fdc_id=fdc_id,
        )
    return out


@lru_cache(maxsize=1)
def default_registry() -> IngredientRegistry:
    """The bundled curated registry, built once."""
    return IngredientRegistry(_build(_CURATED))
