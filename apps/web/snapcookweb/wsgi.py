# SPDX-License-Identifier: AGPL-3.0-or-later
"""WSGI entrypoint. Served by gunicorn; see entrypoint.sh."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "snapcookweb.settings")

application = get_wsgi_application()
