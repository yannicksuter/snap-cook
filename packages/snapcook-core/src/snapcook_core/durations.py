# SPDX-License-Identifier: Apache-2.0
"""How long a recipe takes, read from and written to the words people use.

A recipe states its times in whatever form the source used: "25 Min",
"2 Std. 10", "1 h 30 min", "1.5 h", "30-40 min". They are stored as whole
minutes (:class:`snapcook_core.schema.RecipeTime`) and written back in one
form, "2 h 10 min", which every reader of the Cooklang text can read again.
"""

from __future__ import annotations

import re
from decimal import Decimal

__all__ = ["TIME_KEYS", "minutes_text", "parse_minutes"]

# Frontmatter key -> RecipeTime field.
TIME_KEYS = {
    "prep time": "prep",
    "cook time": "cook",
    "rest time": "rest",
    "total time": "total",
}

_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)")
_PART = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|stunden?|std\.?|minutes?|minuten?|mins?|min\.?|m)?",
    re.IGNORECASE,
)


def parse_minutes(value: object) -> int | None:
    """Whole minutes, or ``None`` for nothing a duration can be read from.

    A number without a unit is minutes. A range counts as its upper end: "ready
    in 30-40 min" is a promise of 40.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = _RANGE.sub(lambda match: match.group(2), str(value))
    total = Decimal(0)
    found = False
    for number, unit in _PART.findall(text):
        amount = Decimal(number.replace(",", "."))
        if unit and unit[0].lower() in "hs":  # h, hours, Std., Stunden
            amount *= 60
        total += amount
        found = True
    return int(total.to_integral_value()) if found else None


def minutes_text(minutes: int) -> str:
    """``25 min``, ``2 h``, ``2 h 10 min``: the same in English and German."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    if not rest:
        return f"{hours} h"
    return f"{hours} h {rest} min"
