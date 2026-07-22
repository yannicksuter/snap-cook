# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-rendered recipe views.

Presentation only. These views hold no domain logic: they call
``snapcook_core`` for rendering and ``catalog.access`` for visibility, then
build a context dict. If domain logic appears here, it is a bug -- move it into
the core package where a Flutter client and the API can reach it too.

The detail view is the thesis made interactive: one stored recipe, re-rendered
on the fly into whatever language, unit system and scale the reader chooses. The
toggles are plain HTMX GETs that swap a fragment, so a reader can flip Rösti from
German-metric to English-US-doubled without the recipe changing on disk.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from catalog.access import get_recipe_or_404, visible_recipes
from snapcook_core.render import (
    RenderOptions,
    build_render_model,
    render_mermaid,
    render_text,
)
from snapcook_core.store import FilesystemStore

_LANGS = [("en", "English"), ("de", "Deutsch")]
_SYSTEMS = [("metric", "Metric"), ("us", "US")]
_SCALES = [(Decimal("0.5"), "½×"), (Decimal(1), "1×"), (Decimal(2), "2×"), (Decimal(3), "3×")]
_MAX_SCALE = Decimal(100)


def index(request: HttpRequest) -> HttpResponse:
    """Recipe list.

    Starts from ``visible_recipes`` rather than ``Recipe.objects`` -- see the
    warning in catalog/access.py.
    """
    recipes = visible_recipes(request.user).select_related("owner")[:50]
    return render(request, "recipes/index.html", {"recipes": recipes})


def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One recipe, rendered for the reader's chosen language, units and scale."""
    catalog_recipe = get_recipe_or_404(request.user, slug)
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = store.head_recipe(catalog_recipe.recipe_id)

    options = _options_from_request(request)
    model = build_render_model(recipe, options)

    context = {
        "recipe": catalog_recipe,
        "model": model,
        "mermaid": render_mermaid(model),
        "plaintext": render_text(model),
        "warnings": [w for w in model.warnings if w.severity in ("warn", "error")],
        "selected": {
            "lang": options.lang,
            "system": options.system,
            "scale": _scale_str(options.scale),
        },
        "langs": _LANGS,
        "systems": _SYSTEMS,
        "scales": [(_scale_str(value), label) for value, label in _SCALES],
    }
    is_htmx = request.headers.get("HX-Request")
    template = "recipes/_render.html" if is_htmx else "recipes/detail.html"
    return render(request, template, context)


def _options_from_request(request: HttpRequest) -> RenderOptions:
    """Read render options from the query string, defaulting to the reader.

    Preferences seed the defaults so a signed-in reader lands on their language
    and units; the query string overrides for a single view without changing
    anything stored.
    """
    prefs = getattr(request.user, "preferences", None)
    default_lang = getattr(prefs, "language", "en")
    default_system = getattr(prefs, "unit_system", "metric")

    lang = request.GET.get("lang", default_lang)
    if lang not in dict(_LANGS):
        lang = default_lang if default_lang in dict(_LANGS) else "en"

    system = request.GET.get("system", default_system)
    if system not in dict(_SYSTEMS):
        system = "metric"

    return RenderOptions(lang=lang, system=system, scale=_parse_scale(request.GET.get("scale")))


def _parse_scale(raw: str | None) -> Decimal:
    if not raw:
        return Decimal(1)
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(1)
    if value <= 0:
        return Decimal(1)
    return min(value, _MAX_SCALE)


def _scale_str(scale: Decimal) -> str:
    if scale == scale.to_integral_value():
        return str(int(scale))
    return format(scale.normalize(), "f")
