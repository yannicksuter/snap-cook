# SPDX-License-Identifier: AGPL-3.0-or-later
"""Product API -- /api/v1/

Mounted only when SNAPCOOK_API_ENABLED=1; otherwise the router is never
included and every path under it returns 404.

.. warning::
   This surface is exempt from LoginRequiredMiddleware. Authorization comes
   entirely from the ``auth=`` declaration below and from
   ``catalog.access.visible_recipes``. An endpoint added without an auth
   declaration is published to the internet.

Session auth sits alongside token auth so the HTMX UI calls the same endpoints
the Flutter client will -- one implementation, not two that drift.
"""

from __future__ import annotations

from ninja import NinjaAPI, Schema
from ninja.security import django_auth

from api.auth import PatAuth

api = NinjaAPI(
    version="1.0.0",
    title="snap-cook",
    description="Structured recipes: model in, any view out.",
    urls_namespace="product",
    auth=[django_auth, PatAuth()],
)


class MeOut(Schema):
    username: str
    email: str
    language: str
    unit_system: str


@api.get("/me", response=MeOut, summary="Current identity and render preferences")
def me(request) -> MeOut:
    user = request.user
    prefs = getattr(user, "preferences", None)
    return MeOut(
        username=user.get_username(),
        email=user.email or "",
        language=getattr(prefs, "language", "en"),
        unit_system=getattr(prefs, "unit_system", "metric"),
    )
