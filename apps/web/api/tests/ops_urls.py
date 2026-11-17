# SPDX-License-Identifier: AGPL-3.0-or-later
"""The site's URLs with the ops API mounted, as SNAPCOOK_OPS_API_ENABLED=1 does.

The real URLconf decides at import time and the test settings leave the ops API
off, so its tests use this one (``@pytest.mark.urls``).
"""

from django.urls import path

from api.ops import api as ops_api
from snapcookweb.urls import urlpatterns as site

urlpatterns = [*site, path("ops/api/", ops_api.urls)]
