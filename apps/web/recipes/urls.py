# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web UI routes.

Every pattern is named so templates never hard-code a path.
"""

from django.urls import path

from recipes import views

app_name = "recipes"

urlpatterns = [
    path("", views.index, name="index"),
    path("r/<slug:slug>/", views.detail, name="detail"),
]
