# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-rendered recipe views.

Presentation only. These views hold no domain logic: they call
``snapcook_core`` for rendering and ``catalog.access`` for visibility, then
build a context dict. If domain logic appears here, it is a bug -- move it into
the core package where a Flutter client and the API can reach it too.

The detail view is the thesis made interactive: one stored recipe, re-rendered
on the fly into whatever language, unit system and number of servings the
reader chooses. The controls are plain links that HTMX turns into fragment
swaps, so a reader can flip Rösti from German-metric to English-US-for-six
without the recipe changing on disk, and the page still works without
JavaScript.

Language and units start from the reader's settings (``request.LANGUAGE_CODE``
already holds the saved language; see ``accounts.middleware``). The query
string overrides them for one view without changing anything stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from catalog.access import get_recipe_or_404, visible_recipes
from imports.models import ImportJob
from snapcook_core.render import (
    RenderOptions,
    build_render_model,
    render_mermaid,
    render_text,
)
from snapcook_core.store import FilesystemStore

_SYSTEMS = ("metric", "us")
# "Show this recipe in X", written in X: a reader looks for their own language,
# not for its name in the language they are trying to leave.
_SHOW_IN = {"en": "Show in English", "de": "Auf Deutsch anzeigen"}
_MAX_SERVINGS = 100
_MAX_SCALE = Decimal(100)
# For a recipe that does not say how many it serves, the stepper walks these.
_SCALE_STEPS = (Decimal("0.5"), Decimal(1), Decimal("1.5"), Decimal(2), Decimal(3), Decimal(4))


@dataclass(frozen=True)
class _Link:
    label: str
    url: str
    lang: str = ""


@dataclass(frozen=True)
class _View:
    """What this reader asked for, and the links that change one thing of it."""

    lang: str
    system: str
    scale: Decimal
    servings: int | None
    amount: str
    fewer: str
    more: str
    languages: tuple[_Link, ...]
    units: _Link


def index(request: HttpRequest) -> HttpResponse:
    """Recipe list, optionally filtered by a search for words in the title or description.

    Starts from ``visible_recipes`` rather than ``Recipe.objects`` -- see the
    warning in catalog/access.py.
    """
    query = request.GET.get("q", "").strip()
    recipes = visible_recipes(request.user).select_related("owner")
    if query:
        recipes = recipes.filter(Q(title__icontains=query) | Q(description__icontains=query))
    # The reader's own unsaved imports: where a draft waits after they left the
    # page that was reading it.
    drafts = ImportJob.objects.filter(owner=request.user).exclude(status=ImportJob.Status.SAVED)
    context = {"recipes": recipes[:50], "query": query, "drafts": drafts[:10]}
    return render(request, "recipes/index.html", context)


def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One recipe, rendered for the reader's language, units and servings."""
    catalog_recipe = get_recipe_or_404(request.user, slug)
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = store.head_recipe(catalog_recipe.recipe_id)

    view = _view_from_request(request, slug, recipe.servings)
    model = build_render_model(
        recipe, RenderOptions(lang=view.lang, system=view.system, scale=view.scale)
    )

    context = {
        "recipe": catalog_recipe,
        "model": model,
        "view": view,
        "mermaid": render_mermaid(model),
        "plaintext": render_text(model),
        "warnings": [w for w in model.warnings if w.severity in ("warn", "error")],
    }
    is_htmx = request.headers.get("HX-Request")
    template = "recipes/_render.html" if is_htmx else "recipes/detail.html"
    return render(request, template, context)


def _view_from_request(request: HttpRequest, slug: str, base_servings: int | None) -> _View:
    languages = dict(settings.LANGUAGES)
    lang = request.GET.get("lang", "")
    if lang not in languages:
        lang = request.LANGUAGE_CODE if request.LANGUAGE_CODE in languages else "en"

    system = request.GET.get("system", "")
    if system not in _SYSTEMS:
        saved = getattr(getattr(request.user, "preferences", None), "unit_system", "metric")
        system = saved if saved in _SYSTEMS else "metric"

    def url(**changes: object) -> str:
        params: dict[str, object] = {"lang": lang, "system": system}
        if base_servings:
            params["servings"] = servings
        else:
            params["scale"] = _scale_str(scale)
        params.update(changes)
        return f"{reverse('recipes:detail', args=[slug])}?{urlencode(params)}"

    if base_servings:
        servings = _parse_servings(request.GET.get("servings"), base_servings)
        scale = Decimal(servings) / Decimal(base_servings)
        amount = str(servings)
        fewer = url(servings=servings - 1) if servings > 1 else ""
        more = url(servings=servings + 1) if servings < _MAX_SERVINGS else ""
    else:
        servings = None
        scale = _parse_scale(request.GET.get("scale"))
        amount = f"{_scale_str(scale)}×"
        smaller = [step for step in _SCALE_STEPS if step < scale]
        larger = [step for step in _SCALE_STEPS if step > scale]
        fewer = url(scale=_scale_str(smaller[-1])) if smaller else ""
        more = url(scale=_scale_str(larger[0])) if larger else ""

    other = "us" if system == "metric" else "metric"
    if other == "us":
        units_label = _("Show in US cups and ounces")
    else:
        units_label = _("Show in grams and millilitres")
    return _View(
        lang=lang,
        system=system,
        scale=scale,
        servings=servings,
        amount=amount,
        fewer=fewer,
        more=more,
        languages=tuple(
            _Link(_SHOW_IN.get(code, name), url(lang=code), lang=code)
            for code, name in settings.LANGUAGES
            if code != lang
        ),
        units=_Link(units_label, url(system=other)),
    )


def _parse_servings(raw: str | None, base: int) -> int:
    try:
        value = int(raw) if raw else base
    except ValueError:
        return base
    return min(max(value, 1), _MAX_SERVINGS)


def _parse_scale(raw: str | None) -> Decimal:
    if not raw:
        return Decimal(1)
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(1)
    if not value.is_finite() or value <= 0:
        return Decimal(1)
    return min(value, _MAX_SCALE)


def _scale_str(scale: Decimal) -> str:
    if scale == scale.to_integral_value():
        return str(int(scale))
    return format(scale.normalize(), "f")
