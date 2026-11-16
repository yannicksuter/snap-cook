# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reader's settings form."""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from accounts.models import UnitSystem, UserPreferences

_RADIO = forms.RadioSelect(attrs={"class": "h-5 w-5 flex-none accent-herb"})


class PreferencesForm(forms.ModelForm):
    """Language and units: the two things a reader sets once.

    The language list is the interface's, from ``settings.LANGUAGES``, so a
    language is offered exactly when the server has a catalogue for it. Units
    offer the systems the recipe page can show; imperial stays in the model for
    the API but has no renderer worth offering yet.
    """

    language = forms.ChoiceField(choices=settings.LANGUAGES, widget=_RADIO, label=_("Language"))
    unit_system = forms.ChoiceField(
        choices=[
            (UnitSystem.METRIC, _("Metric: grams and millilitres")),
            (UnitSystem.US, _("US: cups and ounces")),
        ],
        widget=_RADIO,
        label=_("Units"),
    )

    class Meta:
        model = UserPreferences
        fields = ["language", "unit_system"]
