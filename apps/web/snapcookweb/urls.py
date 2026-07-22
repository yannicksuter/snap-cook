# SPDX-License-Identifier: AGPL-3.0-or-later
"""Root URL configuration.

The two API surfaces are mounted **conditionally**. When a flag is off the
router is not included at all, so a disabled endpoint returns 404 rather than
403 -- a 403 confirms that something exists there, which is information we do
not need to give away.

Two consequences of conditional mounting that bite people:

* ``reverse()`` on an API route raises when the surface is disabled. Templates
  must not hard-link API URLs; guard them.
* A test that toggles a flag needs ``override_settings`` **plus**
  ``clear_url_caches()`` and a reload of this module, because Django caches the
  resolved URLconf. ``api/tests/conftest.py`` provides fixtures that do it
  correctly -- use those rather than rolling your own.

/ops/api/ is deliberately not nested under /api/ so that the two flags, the two
auth models and the reverse-proxy rules stay fully independent: you can expose
/api/ through a public tunnel while keeping /ops/api/ on the LAN only.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from snapcookweb import views

urlpatterns = [
    # Unauthenticated, deliberately. This is the container health probe.
    path("up", views.up, name="up"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("recipes.urls")),
]

if settings.SNAPCOOK_API_ENABLED:
    from api.product import api as product_api

    urlpatterns.append(path("api/v1/", product_api.urls))

if settings.SNAPCOOK_OPS_API_ENABLED:
    from api.ops import api as ops_api

    urlpatterns.append(path("ops/api/", ops_api.urls))
