# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reader's own pages.

Mounted at ``/settings/``, never under ``/accounts/``: that prefix belongs to
allauth and is exempt from ``LoginRequiredMiddleware``.
"""

from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.preferences, name="settings"),
]
