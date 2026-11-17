# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stand-in reader for development and tests: ``SNAPCOOK_LLM_PROVIDER=fake``.

It ignores the source and always "reads" the corpus tomato sauce, with one open
question, so the whole flow -- add, wait, check, save -- can be tried without an
API key or any cost. It "translates" by putting the language in front of every
piece, which keeps the slots of a step in place. Never set it on a server people
use.
"""

from __future__ import annotations

from snapcook_core.cooklang import print_cook
from snapcook_core.importing import Answer, ImportSource, Question, RawExtraction
from snapcook_core.testing import get_recipe
from snapcook_core.translating import RawTranslation, TranslatedPiece, TranslationRequest

__all__ = ["FakeImporter"]


class FakeImporter:
    def extract(self, source: ImportSource) -> RawExtraction:
        text = "\n".join(
            line
            for line in print_cook(get_recipe("004-tomato-sauce")).splitlines()
            if not line.startswith(("visibility:", "description:"))
        )
        text = text.replace("@garlic{2}", "@garlic{2%cloves}").replace(
            "title: Tomato sauce",
            "title: Tomato sauce\ndescription: Onion and garlic softened in olive oil, "
            "then simmered with crushed tomatoes.",
        )
        return RawExtraction(
            is_recipe=True,
            cooklang=text,
            questions=[
                Question(
                    text="How much garlic? The source says “2 garlic”.",
                    answers=[
                        Answer(
                            label="2 cloves", find="@garlic{2%cloves}", replace="@garlic cloves{2}"
                        ),
                        Answer(
                            label="2 heads", find="@garlic{2%cloves}", replace="@garlic heads{2}"
                        ),
                    ],
                )
            ],
            left_out=["the introduction", "the page number"],
            source_title="Fake Cookbook" if source.kind == "files" else None,
        )

    def translate(self, request: TranslationRequest) -> RawTranslation:
        return RawTranslation(
            pieces=[
                TranslatedPiece(key=piece.key, text=f"[{request.target_lang}] {piece.text}")
                for piece in request.pieces
            ]
        )
