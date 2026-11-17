# SPDX-License-Identifier: Apache-2.0
"""Translating a recipe's words into another language, never its structure.

:func:`pending_pieces` lists what a recipe still needs in a language; a
:class:`RecipeTranslator` translates the pieces; :func:`apply_translation`
writes them into the recipe, where :class:`LocalizedText` and the glossary keep
them with the hash of their source. See ``docs/architecture/units-and-i18n.md``.
"""

from snapcook_core.translating.contracts import (
    RawTranslation,
    RecipeTranslator,
    TranslatedPiece,
    TranslationRequest,
)
from snapcook_core.translating.pieces import (
    Piece,
    Translated,
    apply_translation,
    pending_pieces,
)
from snapcook_core.translating.prompt import (
    describe_request,
    language_name,
    translation_prompt,
)

__all__ = [
    "Piece",
    "RawTranslation",
    "RecipeTranslator",
    "TranslatedPiece",
    "Translated",
    "TranslationRequest",
    "apply_translation",
    "describe_request",
    "language_name",
    "pending_pieces",
    "translation_prompt",
]
