# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site-wide login gate, and the reader's interface language.

A middleware rather than per-view decorators, so that a newly added view is
private by default. Forgetting a decorator fails open; forgetting to add a
prefix here fails closed, which is the direction you want the mistake to go.

.. warning::
   ``/api/`` and ``/ops/api/`` are exempt, so **neither API surface receives any
   protection from this middleware**. All API authorization comes from the
   django-ninja auth classes in ``api/product.py`` and from
   ``_require_ops_access`` in ``api/ops.py``. Adding an endpoint without an
   explicit auth declaration publishes it to the internet.

   They are exempt because API clients authenticate with a bearer token and
   must receive a 401 with a JSON body, not a 302 redirect to a Google login
   page that a script cannot follow.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils import translation


class LoginRequiredMiddleware:
    """Redirect anonymous users to Google SSO, except on exempt prefixes."""

    EXEMPT_PREFIXES = (
        "/accounts/",  # allauth's own login flow
        "/admin/",  # Django admin has its own auth
        "/api/",  # bearer-token auth; must not 302
        "/ops/api/",  # bearer-token auth; must not 302
        "/up",  # container health probe
        "/static/",
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated and not self._is_exempt(request.path):
            return redirect(settings.LOGIN_URL)
        return self.get_response(request)

    def _is_exempt(self, path: str) -> bool:
        return path.startswith(self.EXEMPT_PREFIXES)


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
