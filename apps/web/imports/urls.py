# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding a recipe, and the drafts it produces."""

from django.urls import path

from imports import views

app_name = "imports"

urlpatterns = [
    path("add/", views.add, name="add"),
    path("drafts/<uuid:job_id>/", views.status, name="status"),
    path("drafts/<uuid:job_id>/check/", views.review, name="review"),
    path("drafts/<uuid:job_id>/retry/", views.retry, name="retry"),
    path("drafts/<uuid:job_id>/delete/", views.delete, name="delete"),
]
