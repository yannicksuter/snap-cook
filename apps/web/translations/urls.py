# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from translations import views

app_name = "translations"

urlpatterns = [
    path("translations/<uuid:job_id>/", views.status, name="status"),
    path("translations/<uuid:job_id>/retry/", views.retry, name="retry"),
]
