# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who may open which page, and the reader's interface language.

Anyone may read: the recipe list, a recipe and its chart are open without
signing in. Everything else is decided per view by ``AccessMiddleware``, which
fails closed: a view it does not know needs someone who **may cook**, so a newly
added page is never public by mistake. Forgetting to list a view makes it too
strict, which is the direction you want the mistake to go.

.. warning::
   ``/api/`` and ``/ops/api/`` are exempt, so **neither API surface receives any
   protection from this middleware**. All API authorization comes from the
   django-ninja auth classes in ``api/product.py`` and from
   ``_require_ops_access`` in ``api/ops.py``. Adding an endpoint without an
   explicit auth declaration publishes it to the internet.

   They are exempt because API clients authenticate with a bearer token and
   must receive a 401 with a JSON body, not a 302 to a sign-in page that a
   script cannot follow.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation

from accounts.identity import access_for

# Read-only pages anyone may open.
PUBLIC_VIEWS = frozenset({"recipes:index", "recipes:detail", "recipes:chart", "up"})
# Pages for any verified member, cook or not.
MEMBER_VIEWS = frozenset({"accounts:settings"})


class AccessMiddleware:
    """Public, member, cook or admin, by view name; see the module docstring."""

    EXEMPT_PREFIXES = (
        "/accounts/",  # allauth: signing in, up, out, verifying, resetting
        "/api/",  # bearer-token auth; must not 302
        "/ops/api/",  # bearer-token auth; must not 302
        "/static/",
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.access = access_for(request.user)
        return self.get_response(request)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        if request.path.startswith(self.EXEMPT_PREFIXES):
            return None
        name = request.resolver_match.view_name if request.resolver_match else ""
        access = request.access
        if name in PUBLIC_VIEWS:
            return None
        if not access.member:
            return redirect(f"{settings.LOGIN_URL}?{urlencode({'next': request.get_full_path()})}")
        if name in MEMBER_VIEWS:
            return None
        if name.startswith("backoffice:"):
            if access.admin:
                return None
            raise Http404  # no hint that /admin exists
        if access.cook:
            return None
        return render(request, "accounts/not_yet.html", status=403)


class UserLanguageMiddleware:
    """Serve a signed-in reader in the language saved in their settings.

    ``LocaleMiddleware`` runs first and picks a language from the browser's
    ``Accept-Language``. A saved preference outranks it, so the interface
    follows the person rather than the phone they happen to be holding. Without
    a saved preference the browser's choice stands, which is also what a new
    reader's settings page starts from.

    Recipes open in the same language: the recipe view reads
    ``request.LANGUAGE_CODE``, so one setting governs both.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        language = saved_language(request.user)
        if language is not None and language != request.LANGUAGE_CODE:
            translation.activate(language)
            request.LANGUAGE_CODE = language
        return self.get_response(request)


def saved_language(user: object) -> str | None:
    """The user's saved interface language, if it is one this server speaks.

    Anonymous users and users who never saved their settings have none. A saved
    tag the server no longer offers (a language removed from ``LANGUAGES``) is
    ignored rather than trusted, and so is a regional variant without its own
    catalogue: ``de-CH`` resolves to ``de``.
    """
    preferences = getattr(user, "preferences", None)
    if preferences is None or not preferences.language:
        return None
    try:
        return translation.get_supported_language_variant(preferences.language)
    except LookupError:
        return None
