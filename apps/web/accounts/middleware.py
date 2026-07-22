# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site-wide login gate.

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
