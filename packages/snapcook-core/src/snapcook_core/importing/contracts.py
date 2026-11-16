# SPDX-License-Identifier: Apache-2.0
"""The boundary between a model and the rest of the import pipeline.

A :class:`RecipeImporter` turns an :class:`ImportSource` (a page, photos or
pasted text) into a :class:`RawExtraction`. Everything model-specific stays on
the importer's side of the line; everything after it is ordinary code with
ordinary tests. See ``services/llm/docs/interface.md``.

The extraction carries the recipe as text in snap-cook's Cooklang dialect, the
format ``snapcook_core.cooklang`` already parses and prints. A model writes that
format well from a few examples, and the parser then does the hard part --
building and validating the graph -- in code rather than in a prompt. Around
the recipe text sit the things a person must see before saving: open questions,
what was left out, and where the photo of the dish is.

:class:`RawExtraction` doubles as the JSON schema a provider asks the model to
fill, so its field descriptions are written to the model as much as to a reader.
Integers stand in for fractions (per mille), because ``float`` is banned from
every schema in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field

__all__ = [
    "Answer",
    "DishPhoto",
    "ImportFile",
    "ImportSource",
    "Question",
    "RawExtraction",
    "RecipeImporter",
]

CupSize = Literal["us", "metric", "uk", "jp"]


@dataclass(frozen=True)
class ImportFile:
    """One uploaded file: a photo of a page, a screenshot, or a PDF."""

    data: bytes
    media_type: str
    """``image/jpeg``, ``image/png``, ``image/webp``, ``image/gif`` or ``application/pdf``."""


@dataclass(frozen=True)
class ImportSource:
    """What the reader gave us, already fetched and read into memory.

    A provider never fetches anything itself: the web app fetches a page,
    checks where it may connect, and hands over the result. That keeps every
    provider -- hosted or local -- equally unable to reach the network.
    """

    kind: Literal["page", "files", "text"]
    url: str | None = None
    title: str | None = None
    structured: tuple[str, ...] = ()
    """JSON-LD recipe objects found on a page, verbatim. Often the cleanest
    statement of the recipe, when a site provides one."""
    text: str = ""
    """The page's readable text, or the text the reader pasted."""
    files: tuple[ImportFile, ...] = field(default=())


class Answer(BaseModel):
    """One way to settle a question, as an exact edit to the Cooklang text."""

    label: str = Field(description="What the reader taps, short: '2 cloves'.")
    find: str = Field(
        description="A piece of your Cooklang text, copied exactly, that this answer changes."
    )
    replace: str = Field(description="What that piece becomes: '@garlic{2%cloves}'.")


class Question(BaseModel):
    """Something the source leaves open that changes how the dish turns out."""

    text: str = Field(
        description=(
            "The question, in the recipe's language, naming what the source says: "
            "'How much garlic? The page says “2 garlic”.'"
        )
    )
    answers: list[Answer] = Field(description="Two or three likely answers.")


class DishPhoto(BaseModel):
    """Where a picture of the finished dish is, in one of the reader's photos."""

    file: int = Field(description="Which photo, counting from 0 in the order given.")
    left: int = Field(description="Left edge, in thousandths of the photo's width.")
    top: int = Field(description="Top edge, in thousandths of the photo's height.")
    right: int = Field(description="Right edge, in thousandths of the photo's width.")
    bottom: int = Field(description="Bottom edge, in thousandths of the photo's height.")


class RawExtraction(BaseModel):
    """A model's best reading of a source. Never trusted: ``normalize`` decides."""

    is_recipe: bool = Field(description="False when the source holds no recipe at all.")
    cooklang: str = Field(
        description="The recipe in snap-cook's Cooklang dialect, or empty if there is none."
    )
    cups: CupSize | None = Field(
        default=None,
        description=(
            "If the recipe measures in cups, which cup: us (American, 236.6 ml), "
            "metric (Australia, Canada, New Zealand, 250 ml), uk (284 ml), jp (200 ml)."
        ),
    )
    questions: list[Question] = Field(
        default_factory=list,
        description="Only what changes the result and the source leaves open. Often none.",
    )
    left_out: list[str] = Field(
        default_factory=list,
        description="What you dropped, a few words each: 'the story before the recipe'.",
    )
    source_title: str | None = Field(
        default=None,
        description="The book or website the recipe is from, if the source shows it.",
    )
    source_author: str | None = Field(
        default=None, description="The recipe's author, if the source names one."
    )
    dish_photo: DishPhoto | None = Field(
        default=None,
        description="Where the photo of the finished dish is, if one of the photos shows it.",
    )


class RecipeImporter(Protocol):
    """Anything that can read a source: a hosted model, a local one, a test fake."""

    def extract(self, source: ImportSource) -> RawExtraction: ...
