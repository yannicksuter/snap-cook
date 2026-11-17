# SPDX-License-Identifier: Apache-2.0
"""What goes to a translator and what comes back.

The model-specific part is one call behind :class:`RecipeTranslator`, as for
importing. Its answer is checked piece by piece in
:func:`snapcook_core.translating.apply_translation`, which trusts none of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from snapcook_core.translating.pieces import Piece

__all__ = ["RawTranslation", "RecipeTranslator", "TranslatedPiece", "TranslationRequest"]


@dataclass(frozen=True)
class TranslationRequest:
    source_lang: str
    target_lang: str
    pieces: tuple[Piece, ...]


class TranslatedPiece(BaseModel):
    key: str
    text: str


class RawTranslation(BaseModel):
    """Every piece the translator was given, with its key, translated."""

    pieces: list[TranslatedPiece]


class RecipeTranslator(Protocol):
    def translate(self, request: TranslationRequest) -> RawTranslation: ...
