# SPDX-License-Identifier: Apache-2.0
"""The M1 corpus: six recipes, ordered by what each one exercises.

The corpus is the thesis test made concrete. Each recipe earns its place by
covering a case the renderers and units have to get right, from a degenerate
linear list up to the branching, bilingual Rösti the milestone's acceptance
criterion names.

    001 boiled egg      the degenerate DAG: a linear step list, counts
    002 simple syrup    a mass+volume mix, a range, unit conversion
    003 herb omelette   an approximation, cookware, a timer, a temperature
    004 tomato sauce    a real join: two prepped states combined
    005 pancakes        a named intermediate ("the batter"), scaling
    006 roesti          all of it, authored in German, rendered in both

Ids are stable readable slugs rather than minted ULIDs, so the corpus is
reproducible: the same recipe hashes to the same value on every run, which is
what lets golden files and a seeded store stay put. Nothing validates id format
at the schema layer, so this is legal and far kinder to a reader of the store.
"""

from __future__ import annotations

from snapcook_core.schema.quantity import ApproxToken, ScalingPolicy, SizeGrade
from snapcook_core.schema.recipe import Recipe
from snapcook_core.testing.builders import Chef

__all__ = ["CORPUS", "corpus_recipes", "get_recipe"]


def _boiled_egg() -> Recipe:
    c = Chef("en")
    egg = c.ingredient("iuse_egg_egg", "ing_egg", "eggs", c.count(2))
    water = c.ingredient(
        "iuse_egg_water", "ing_water", "water", c.scalar(1, "unit:l", "l", ScalingPolicy.INVARIANT)
    )
    salt = c.ingredient("iuse_egg_salt", "ing_salt", "salt", c.approx(ApproxToken.PINCH, "a pinch"))

    boiling = c.state("nod_egg_boiling", en="boiling water")
    a1 = c.step(
        "act_egg_1",
        boiling,
        order=0,
        verb=c.t(en="boil"),
        ingredients=[water, salt],
        text=c.prose(
            c.lit(en="Bring "),
            c.ref("iuse_egg_water"),
            c.lit(en=" with "),
            c.ref("iuse_egg_salt"),
            c.lit(en=" to a rolling boil."),
        ),
    )
    done = c.state("nod_egg_done", en="soft-boiled eggs")
    a2 = c.step(
        "act_egg_2",
        done,
        order=1,
        uses=["nod_egg_boiling"],
        verb=c.t(en="cook"),
        ingredients=[egg],
        text=c.prose(
            c.lit(en="Lower "),
            c.ref("iuse_egg_egg"),
            c.lit(en=" into the "),
            c.consume("nod_egg_boiling"),
            c.lit(en=" and simmer 6 minutes for a soft yolk."),
        ),
    )
    return Recipe(
        id="rcp_001_boiled_egg",
        source_lang="en",
        visibility="public",
        servings=2,
        title=c.t(en="Soft-boiled egg"),
        description=c.t(
            en="The simplest recipe there is: proof that a linear list is just a degenerate graph."
        ),
        tags=["breakfast", "basics"],
        actions=[a1, a2],
    )


def _simple_syrup() -> Recipe:
    c = Chef("en")
    sugar = c.ingredient("iuse_syr_sugar", "ing_sugar", "sugar", c.scalar(200, "unit:g", "g"))
    water = c.ingredient("iuse_syr_water", "ing_water", "water", c.range(200, 250, "unit:ml", "ml"))
    syrup = c.state("nod_syr_done", en="simple syrup")
    a1 = c.step(
        "act_syr_1",
        syrup,
        order=0,
        verb=c.t(en="dissolve"),
        ingredients=[sugar, water],
        text=c.prose(
            c.lit(en="Warm "),
            c.ref("iuse_syr_water"),
            c.lit(en=" and stir in "),
            c.ref("iuse_syr_sugar"),
            c.lit(en=" until fully dissolved and clear."),
        ),
    )
    return Recipe(
        id="rcp_002_simple_syrup",
        source_lang="en",
        visibility="public",
        servings=1,
        title=c.t(en="Simple syrup"),
        description=c.t(
            en="Equal-ish parts sugar and water — a one-step recipe that still needs "
            "mass, volume and a range."
        ),
        tags=["basics", "sweet"],
        actions=[a1],
    )


def _herb_omelette() -> Recipe:
    c = Chef("en")
    eggs = c.ingredient("iuse_om_eggs", "ing_egg", "eggs", c.count(3))
    salt = c.ingredient(
        "iuse_om_salt", "ing_salt", "salt", c.approx(ApproxToken.TO_TASTE, "to taste")
    )
    pepper = c.ingredient(
        "iuse_om_pepper", "ing_pepper", "pepper", c.approx(ApproxToken.TO_TASTE, "to taste")
    )
    butter = c.ingredient("iuse_om_butter", "ing_butter", "butter", c.scalar(15, "unit:g", "g"))

    beaten = c.state("nod_om_beaten", en="beaten eggs")
    a1 = c.step(
        "act_om_1",
        beaten,
        order=0,
        verb=c.t(en="beat"),
        ingredients=[eggs, salt, pepper],
        text=c.prose(
            c.lit(en="Beat "),
            c.ref("iuse_om_eggs"),
            c.lit(en=" with "),
            c.ref("iuse_om_salt"),
            c.lit(en=" and "),
            c.ref("iuse_om_pepper"),
            c.lit(en="."),
        ),
    )
    pan = c.cookware("cwu_om_pan", en="non-stick pan")
    done = c.state("nod_om_done", en="omelette")
    a2 = c.step(
        "act_om_2",
        done,
        order=1,
        uses=["nod_om_beaten"],
        verb=c.t(en="cook"),
        ingredients=[butter],
        cookware=[pan],
        timers=[c.timer(c.scalar(3, "unit:min", "min"))],
        temperatures=[c.temp(160)],
        text=c.prose(
            c.lit(en="Melt "),
            c.ref("iuse_om_butter"),
            c.lit(en=" in the "),
            c.tool("cwu_om_pan"),
            c.lit(en=" at "),
            c.temp_slot(0),
            c.lit(en=", pour in the "),
            c.consume("nod_om_beaten"),
            c.lit(en=" and cook for "),
            c.timer_slot(0),
            c.lit(en="."),
        ),
    )
    return Recipe(
        id="rcp_003_herb_omelette",
        source_lang="en",
        visibility="public",
        servings=1,
        title=c.t(en="Herb omelette"),
        description=c.t(en="Approximations, a pan, a timer and a temperature in one small dish."),
        tags=["breakfast"],
        actions=[a1, a2],
    )


def _tomato_sauce() -> Recipe:
    c = Chef("en")
    onion = c.ingredient("iuse_ts_onion", "ing_onion", "onion", c.count(1, SizeGrade.MEDIUM))
    garlic = c.ingredient("iuse_ts_garlic", "ing_garlic", "garlic", c.count(2))
    oil = c.ingredient(
        "iuse_ts_oil", "ing_olive_oil", "olive oil", c.scalar(2, "unit:tbsp", "tbsp")
    )
    tomato = c.ingredient("iuse_ts_tomato", "ing_tomato", "tomatoes", c.count(6))
    salt = c.ingredient(
        "iuse_ts_salt", "ing_salt", "salt", c.approx(ApproxToken.TO_TASTE, "to taste")
    )

    softened = c.state("nod_ts_softened", en="softened aromatics")
    a1 = c.step(
        "act_ts_1",
        softened,
        order=0,
        verb=c.t(en="sweat"),
        ingredients=[oil, onion, garlic],
        text=c.prose(
            c.lit(en="Warm "),
            c.ref("iuse_ts_oil"),
            c.lit(en=" and soften "),
            c.ref("iuse_ts_onion"),
            c.lit(en=" and "),
            c.ref("iuse_ts_garlic"),
            c.lit(en=" without colouring."),
        ),
    )
    crushed = c.state("nod_ts_crushed", en="crushed tomatoes")
    a2 = c.step(
        "act_ts_2",
        crushed,
        order=1,
        verb=c.t(en="crush"),
        ingredients=[tomato],
        text=c.prose(c.lit(en="Crush "), c.ref("iuse_ts_tomato"), c.lit(en=" by hand.")),
    )
    sauce = c.state("nod_ts_sauce", en="tomato sauce")
    a3 = c.step(
        "act_ts_3",
        sauce,
        order=2,
        uses=["nod_ts_softened", "nod_ts_crushed"],
        verb=c.t(en="simmer"),
        ingredients=[salt],
        timers=[c.timer(c.scalar(30, "unit:min", "min"))],
        text=c.prose(
            c.lit(en="Combine the "),
            c.consume("nod_ts_softened"),
            c.lit(en=" with the "),
            c.consume("nod_ts_crushed"),
            c.lit(en=", season with "),
            c.ref("iuse_ts_salt"),
            c.lit(en=" and simmer for "),
            c.timer_slot(0),
            c.lit(en="."),
        ),
    )
    return Recipe(
        id="rcp_004_tomato_sauce",
        source_lang="en",
        visibility="public",
        servings=4,
        title=c.t(en="Tomato sauce"),
        description=c.t(
            en="Two states prepared apart, then joined — the first genuinely non-linear recipe."
        ),
        tags=["sauce", "italian"],
        actions=[a1, a2, a3],
    )


def _pancakes() -> Recipe:
    c = Chef("en")
    flour = c.ingredient("iuse_pc_flour", "ing_flour", "flour", c.scalar(200, "unit:g", "g"))
    milk = c.ingredient("iuse_pc_milk", "ing_milk", "milk", c.scalar(300, "unit:ml", "ml"))
    egg = c.ingredient("iuse_pc_egg", "ing_egg", "eggs", c.count(2))
    sugar = c.ingredient("iuse_pc_sugar", "ing_sugar", "sugar", c.scalar(1, "unit:tbsp", "tbsp"))
    butter = c.ingredient(
        "iuse_pc_butter",
        "ing_butter",
        "butter",
        c.scalar(20, "unit:g", "g", ScalingPolicy.INVARIANT),
    )

    batter = c.state("nod_pc_batter", en="the batter")
    a1 = c.step(
        "act_pc_1",
        batter,
        order=0,
        verb=c.t(en="whisk"),
        ingredients=[flour, milk, egg, sugar],
        text=c.prose(
            c.lit(en="Whisk "),
            c.ref("iuse_pc_flour"),
            c.lit(en=", "),
            c.ref("iuse_pc_milk"),
            c.lit(en=", "),
            c.ref("iuse_pc_egg"),
            c.lit(en=" and "),
            c.ref("iuse_pc_sugar"),
            c.lit(en=" into a smooth batter and rest it 15 minutes."),
        ),
    )
    pan = c.cookware("cwu_pc_pan", en="frying pan")
    done = c.state("nod_pc_done", en="pancakes")
    a2 = c.step(
        "act_pc_2",
        done,
        order=1,
        uses=["nod_pc_batter"],
        verb=c.t(en="fry"),
        ingredients=[butter],
        cookware=[pan],
        temperatures=[c.temp(180)],
        text=c.prose(
            c.lit(en="Fry ladles of "),
            c.consume("nod_pc_batter"),
            c.lit(en=" in "),
            c.ref("iuse_pc_butter"),
            c.lit(en=" in a "),
            c.tool("cwu_pc_pan"),
            c.lit(en=" at "),
            c.temp_slot(0),
            c.lit(en=" until golden on both sides."),
        ),
    )
    return Recipe(
        id="rcp_005_pancakes",
        source_lang="en",
        visibility="public",
        servings=4,
        title=c.t(en="Pancakes"),
        description=c.t(
            en="A named intermediate — the batter — and a butter that must not "
            "scale with the batch."
        ),
        tags=["breakfast", "sweet"],
        actions=[a1, a2],
    )


def _roesti() -> Recipe:
    c = Chef("de")
    potato = c.ingredient(
        "iuse_ro_potato", "ing_potato", "Kartoffeln", c.scalar(800, "unit:g", "g")
    )
    onion = c.ingredient("iuse_ro_onion", "ing_onion", "Zwiebel", c.count(1, SizeGrade.MEDIUM))
    salt = c.ingredient(
        "iuse_ro_salt", "ing_salt", "Salz", c.approx(ApproxToken.TO_TASTE, "nach Geschmack")
    )
    pepper = c.ingredient(
        "iuse_ro_pepper",
        "ing_pepper",
        "Pfeffer",
        c.approx(ApproxToken.TO_TASTE, "nach Geschmack"),
        optional=True,
    )
    butter = c.ingredient("iuse_ro_butter", "ing_butter", "Butter", c.scalar(40, "unit:g", "g"))

    grated = c.state("nod_ro_grated", en="grated potatoes", de="geriebene Kartoffeln")
    a1 = c.step(
        "act_ro_1",
        grated,
        order=0,
        verb=c.t(en="grate", de="reiben"),
        ingredients=[potato, onion, salt, pepper],
        text=c.prose(
            c.lit(en="Coarsely grate ", de="Reiben Sie "),
            c.ref("iuse_ro_potato"),
            c.lit(en=" and ", de=" und "),
            c.ref("iuse_ro_onion"),
            c.lit(en=", then season with ", de=" grob, dann würzen Sie mit "),
            c.ref("iuse_ro_salt"),
            c.lit(en=" and ", de=" und "),
            c.ref("iuse_ro_pepper"),
            c.lit(en=".", de="."),
        ),
    )
    pan = c.cookware("cwu_ro_pan", en="frying pan", de="Bratpfanne")
    roesti = c.state("nod_ro_done", en="rösti", de="Rösti")
    a2 = c.step(
        "act_ro_2",
        roesti,
        order=1,
        uses=["nod_ro_grated"],
        verb=c.t(en="fry", de="braten"),
        ingredients=[butter],
        cookware=[pan],
        timers=[c.timer(c.scalar(15, "unit:min", "min"))],
        temperatures=[c.temp(180)],
        text=c.prose(
            c.lit(en="Melt ", de="Schmelzen Sie "),
            c.ref("iuse_ro_butter"),
            c.lit(en=" in the ", de=" in der "),
            c.tool("cwu_ro_pan"),
            c.lit(en=" at ", de=" bei "),
            c.temp_slot(0),
            c.lit(en=", add the ", de=", geben Sie die "),
            c.consume("nod_ro_grated"),
            c.lit(
                en=", press flat and fry for ",
                de=" hinein, drücken flach und braten Sie ",
            ),
            c.timer_slot(0),
            c.lit(
                en=" until the underside is golden, then flip.",
                de=" bis die Unterseite goldbraun ist, dann wenden.",
            ),
        ),
    )
    return Recipe(
        id="rcp_006_roesti",
        source_lang="de",
        visibility="public",
        servings=2,
        title=c.t(en="Rösti", de="Rösti"),
        description=c.t(
            en="The Swiss potato classic — the milestone's acceptance recipe, "
            "authored in German and read in both languages.",
            de="Der Schweizer Kartoffelklassiker.",
        ),
        tags=["swiss", "potato", "vegetarian"],
        actions=[a1, a2],
    )


_BUILDERS = {
    "001-boiled-egg": _boiled_egg,
    "002-simple-syrup": _simple_syrup,
    "003-herb-omelette": _herb_omelette,
    "004-tomato-sauce": _tomato_sauce,
    "005-pancakes": _pancakes,
    "006-roesti": _roesti,
}

CORPUS: dict[str, Recipe] = {slug: build() for slug, build in _BUILDERS.items()}


def corpus_recipes() -> list[Recipe]:
    """Every corpus recipe, in slug order."""
    return [CORPUS[slug] for slug in sorted(CORPUS)]


def get_recipe(slug: str) -> Recipe:
    return CORPUS[slug]
