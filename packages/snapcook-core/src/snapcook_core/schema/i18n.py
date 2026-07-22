# SPDX-License-Identifier: Apache-2.0
"""Localised prose and per-string staleness.

Two kinds of text live in a recipe and they are internationalised differently:

*Ingredient names* resolve through the ingredient registry at render time --
``binding.ingredient_id -> Ingredient.names[lang]`` -- so "flour" and "Mehl"
are one entity seen in two languages, never two strings to keep in sync.

*Prose* -- the title, the description, the literal text between the ingredient
slots in a step -- is genuinely authored per language and is carried by
:class:`LocalizedText`. Its structure is deliberately constrained so a
translation cannot drift structurally from its source: the *chunk sequence* of a
step is shared across languages (see :mod:`snapcook_core.schema.graph`); only the
literal text inside a chunk is translated.

Staleness is tracked **per string**. Each non-source translation records the
hash of the source string it was translated from. Fixing a typo in the source
invalidates exactly the translations of that one string, not a whole language --
which is what makes a large translation survive small edits.
"""

from __future__ import annotations

import hashlib
import unicodedata

from pydantic import model_validator

from snapcook_core.schema.base import SnapcookModel

__all__ = ["LocalizedText", "source_string_hash"]


def source_string_hash(text: str) -> str:
    """Stable hash of a source string, for staleness detection.

    NFC-normalised first, so the same word typed on macOS (decomposed) and
    Linux (composed) produces one hash and does not spuriously mark every
    translation stale. Deliberately *not* the ``sc1:`` content hash -- this is
    a per-string marker, not a recipe identity, and keeping the two namespaces
    separate stops one being mistaken for the other.
    """
    normalized = unicodedata.normalize("NFC", text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class LocalizedText(SnapcookModel):
    """A short piece of prose in one or more languages.

    ``values`` maps a BCP-47 language tag to the string. ``source`` names the
    language the recipe was authored in and must be present in ``values`` -- a
    translation with no source cannot be checked for staleness, and text with no
    authoritative form is a translation of nothing.

    ``stale_against`` records, for each non-source language, the
    :func:`source_string_hash` of the source string at the time it was
    translated. A renderer compares it to the current source hash and flags a
    translation whose source has since changed.
    """

    source: str
    values: dict[str, str]
    stale_against: dict[str, str] = {}

    @model_validator(mode="after")
    def _source_is_present(self) -> LocalizedText:
        if self.source not in self.values:
            raise ValueError(
                f"LocalizedText source language {self.source!r} is missing from "
                f"values {sorted(self.values)}"
            )
        return self

    @classmethod
    def mono(cls, lang: str, text: str) -> LocalizedText:
        """Single-language text. The common case while authoring."""
        return cls(source=lang, values={lang: text})

    def resolve(self, lang: str, *, source: str | None = None) -> tuple[str, bool]:
        """Best available string for ``lang`` and whether it is a fallback.

        The chain is: exact tag, then the bare language (``en-US`` -> ``en``),
        then the recipe's source language, then this text's own source. The
        boolean is ``True`` when the returned string is not in the requested
        language, so a renderer can mark fallen-back prose rather than passing it
        off as a real translation.
        """
        if lang in self.values:
            return self.values[lang], False

        base = lang.split("-", 1)[0]
        if base != lang and base in self.values:
            return self.values[base], True

        if source and source in self.values:
            return self.values[source], True

        return self.values[self.source], True

    def is_stale(self, lang: str) -> bool:
        """True if ``lang``'s translation was made against an older source."""
        recorded = self.stale_against.get(lang)
        if recorded is None:
            return False
        return recorded != source_string_hash(self.values[self.source])
