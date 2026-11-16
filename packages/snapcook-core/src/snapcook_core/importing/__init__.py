# SPDX-License-Identifier: Apache-2.0
"""Importing: from a page, photos or pasted text to a draft a person checks.

The model-specific part is one call behind :class:`RecipeImporter`. What it
returns, a :class:`RawExtraction`, is never trusted: :func:`normalize` parses it
into a private draft and reports what it could not read. See
``docs/architecture/import-pipeline.md``.
"""

from snapcook_core.importing.contracts import (
    Answer,
    DishPhoto,
    ImportFile,
    ImportSource,
    Question,
    RawExtraction,
    RecipeImporter,
)
from snapcook_core.importing.normalize import (
    NOT_A_RECIPE,
    UNREADABLE,
    Draft,
    apply_answer,
    normalize,
    read_draft,
    tidy_amounts,
    with_details,
)
from snapcook_core.importing.prompt import describe_source, system_prompt

__all__ = [
    "NOT_A_RECIPE",
    "UNREADABLE",
    "Answer",
    "DishPhoto",
    "Draft",
    "ImportFile",
    "ImportSource",
    "Question",
    "RawExtraction",
    "RecipeImporter",
    "apply_answer",
    "describe_source",
    "normalize",
    "read_draft",
    "system_prompt",
    "tidy_amounts",
    "with_details",
]
