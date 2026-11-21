# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reader's settings page."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts.forms import PreferencesForm
from accounts.identity import mask
from accounts.models import UserPreferences


@require_http_methods(["GET", "POST"])
def preferences(request: HttpRequest) -> HttpResponse:
    """Language and units, set once per person rather than on every recipe."""
    instance = _preferences_for(request)
    if request.method == "POST":
        form = PreferencesForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            # Confirm in the language just chosen, not the one being left.
            translation.activate(form.cleaned_data["language"])
            messages.success(request, _("Saved."))
            return redirect("accounts:settings")
    else:
        form = PreferencesForm(instance=instance)
    context = {"form": form, "masked_email": mask(request.user.email)}
    return render(request, "accounts/settings.html", context)


def _preferences_for(request: HttpRequest) -> UserPreferences:
    try:
        return request.user.preferences
    except UserPreferences.DoesNotExist:
        # Unsaved until the reader presses Save, so looking writes nothing. It
        # starts from what the reader sees now: the browser's language.
        return UserPreferences(user=request.user, language=request.LANGUAGE_CODE)
