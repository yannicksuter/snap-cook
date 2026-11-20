# SPDX-License-Identifier: Apache-2.0
"""The recipe as a chart: numbered steps, ingredients flowing in, the dish last.

An imported recipe has no verbs, so the chart cannot lean on them: a step is
named by the start of its own words, and nothing on the chart is English unless
the reader's language is.
"""

from __future__ import annotations

from snapcook_core.cooklang import parse_cook
from snapcook_core.render import RenderOptions, build_render_model, render_mermaid

_KAESEKUCHEN = """---
title: Käsekuchen
lang: de
---
@Mehl{250%g} und @Butter{125%g} zu einem glatten Teig verkneten. => Teig

Den @&{Teig} in die #Springform{} drücken. => Boden

@Magerquark{1%kg} und @Zucker{200%g} glatt rühren. => Quarkmasse

Die @&{Quarkmasse} auf den @&{Boden} geben und sofort im vorgeheizten Ofen \
(zweite Schiene von unten) ~{55%min} bei ^conventional{175%C} (^fan{155%C}) backen.
"""


def _graph(lang: str = "de"):
    return build_render_model(parse_cook(_KAESEKUCHEN), RenderOptions(lang=lang)).graph


def _nodes(kind: str, lang: str = "de"):
    return [node for node in _graph(lang).nodes if node.kind == kind]


def test_a_german_chart_has_no_english_placeholders() -> None:
    text = render_mermaid(build_render_model(parse_cook(_KAESEKUCHEN), RenderOptions(lang="de")))
    assert not any(word in text for word in ("combine", "step ", "start"))


def test_steps_are_numbered_as_in_the_method() -> None:
    steps = _nodes("step")
    assert [step.number for step in steps] == [1, 2, 3, 4]
    assert steps[0].label == "Mehl und Butter zu einem glatten Teig verkneten"


def test_a_long_step_keeps_its_start_and_its_verb() -> None:
    last = _nodes("step")[-1].label
    assert last.startswith("Die Quarkmasse auf den Boden geben")
    assert " … " in last
    assert last.endswith("backen")


def test_named_results_get_shapes_and_the_dish_closes_the_chart() -> None:
    assert [node.label for node in _nodes("state")] == ["Teig", "Boden", "Quarkmasse"]
    assert [node.label for node in _nodes("dish")] == ["Käsekuchen"]
    graph = _graph()
    (dish,) = _nodes("dish")
    assert [edge.src for edge in graph.edges if edge.dst == dish.id] == [_nodes("step")[-1].id]


def test_amounts_times_and_oven_settings_are_parts_of_their_shapes() -> None:
    quark = next(node for node in _nodes("ingredient") if node.label == "Magerquark")
    assert (quark.amount, quark.amount_after) == ("1 kg", False)
    last = _nodes("step")[-1]
    assert last.times == ("55 min",)
    assert [(t.display, t.mode) for t in last.temperatures] == [
        ("175 °C Ober-/Unterhitze", "conventional"),
        ("155 °C Umluft", "fan"),
    ]
    english = _nodes("step", lang="en")[-1].temperatures
    assert [t.display for t in english] == ["175 °C conventional", "155 °C fan"]


def test_a_temperature_chip_names_its_oven_setting_for_its_symbol() -> None:
    chart = render_mermaid(build_render_model(parse_cook(_KAESEKUCHEN), RenderOptions(lang="de")))
    assert "<span class='temp m-conventional'>175 °C Ober-/Unterhitze</span>" in chart
    assert "<span class='temp m-fan'>155 °C Umluft</span>" in chart


def test_a_recipes_words_never_become_markup() -> None:
    text = """---\ntitle: T\nlang: de\n---\n@<b>Salz</b>{1%g} "einrühren".\n"""
    chart = render_mermaid(build_render_model(parse_cook(text), RenderOptions(lang="de")))
    assert "<b>" not in chart
    assert "#lt;b#gt;Salz#lt;/b#gt;" in chart
    assert "#quot;einrühren#quot;" in chart
