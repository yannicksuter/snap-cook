# SPDX-License-Identifier: AGPL-3.0-or-later
"""The admin pages at /admin; every view here is admin-only (AccessMiddleware)."""

from django.urls import path

from backoffice import views

app_name = "backoffice"

urlpatterns = [
    path("", views.people, name="people"),
    path("people/<int:pk>/cook/", views.set_cook, name="set_cook"),
    path("people/<int:pk>/delete/", views.delete_person, name="delete_person"),
    path("recipes/", views.recipes, name="recipes"),
    path("recipes/<str:recipe_id>/read-again/", views.read_again, name="read_again"),
    path("archive/", views.archive, name="archive"),
    path("archive/<str:recipe_id>/assign/", views.assign, name="assign"),
]
