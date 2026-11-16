# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three ways in -- a link, photos, pasted text -- and the check before saving."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

__all__ = ["DetailsForm", "FilesForm", "LinkForm", "TextForm", "sniff"]

MAX_FILES = 6
# The API takes images up to 10 MB once base64-encoded, which is 7.5 MB raw.
MAX_FILE_BYTES = 7 * 1024 * 1024
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
}
_HEIC_BRANDS = (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1", b"ftypmsf1")


def sniff(head: bytes) -> str | None:
    """The file's real type from its first bytes. The name and the browser can lie."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    return None


class LinkForm(forms.Form):
    url = forms.URLField(max_length=2000, assume_scheme="https", label=_("Link to a recipe"))


class TextForm(forms.Form):
    text = forms.CharField(
        max_length=100_000,
        widget=forms.Textarea(attrs={"rows": 8}),
        label=_("Recipe text"),
        strip=True,
    )


class _MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class _MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("widget", _MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class FilesForm(forms.Form):
    files = _MultipleFileField(label=_("Photos"))

    def clean_files(self) -> list[tuple[object, str]]:
        """Each upload with its sniffed type; refuses what the model cannot read."""
        files = [upload for upload in self.cleaned_data["files"] if upload]
        if not files:
            raise ValidationError(_("Choose at least one photo."))
        if len(files) > MAX_FILES:
            raise ValidationError(_("At most %(count)s photos at once.") % {"count": MAX_FILES})
        checked = []
        for upload in files:
            if upload.size > MAX_FILE_BYTES:
                raise ValidationError(_("Each photo can be at most 7 MB."))
            head = upload.read(16)
            upload.seek(0)
            media_type = sniff(head)
            if media_type is None:
                if head[4:12] in _HEIC_BRANDS:
                    raise ValidationError(
                        _("This is an iPhone HEIC photo. Choose it from the photo picker, "
                          "which sends a JPEG, or set the camera to “Most Compatible”.")
                    )  # fmt: skip
                raise ValidationError(_("Use a photo (JPEG, PNG, WebP, GIF) or a PDF."))
            checked.append((upload, media_type))
        return checked


class DetailsForm(forms.Form):
    """What a reviewer can change before saving: the details, and the text itself."""

    title = forms.CharField(max_length=200, label=_("Name"))
    description = forms.CharField(
        max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Short description"),
    )  # fmt: skip
    servings = forms.IntegerField(min_value=1, max_value=100, required=False, label=_("Serves"))
    cooklang = forms.CharField(
        max_length=100_000, widget=forms.Textarea(attrs={"rows": 14}), label=_("Recipe text")
    )
