# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sentences about a recipe's structure, in the reader's language.

Kept trivial on purpose. Which steps build on which, and which can run side by
side, is decided in the core render model (``RenderedStep.after``,
``RenderModel.side_by_side``); these tags only put the numbers into words.
"""

from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from recipes.oven import oven_mask_css, oven_svg

register = template.Library()


@register.simple_tag
def side_by_side_hint(run: tuple[int, ...]) -> str:
    """'Steps 1 and 2 don't depend on each other…' for one run of steps."""
    if len(run) == 2:
        return _(
            "Steps %(first)s and %(last)s don’t depend on each other, so you can do them "
            "side by side."
        ) % {"first": run[0], "last": run[-1]}
    return _(
        "Steps %(first)s to %(last)s don’t depend on each other, so you can do them side by side."
    ) % {"first": run[0], "last": run[-1]}


@register.simple_tag
def builds_on(step) -> str:
    """'Uses what you made in steps 1 and 2.', or nothing when it goes without saying.

    A step that only continues the one right before it is the normal case and
    needs no sentence. One that joins several results, or picks up something
    made further back, is where a cook loses track.
    """
    after = step.after
    if not after or after == (step.index - 1,):
        return ""
    if len(after) == 1:
        return _("Uses what you made in step %(number)s.") % {"number": after[0]}
    numbers = _("%(list)s and %(last)s") % {
        "list": ", ".join(str(number) for number in after[:-1]),
        "last": after[-1],
    }
    return _("Uses what you made in steps %(numbers)s.") % {"numbers": numbers}


@register.simple_tag
def oven_icon(mode: str | None, size: int = 22) -> str:
    """An oven setting's symbol, inline. Built from constants, so safe to emit."""
    return mark_safe(oven_svg(mode, size))  # noqa: S308


@register.simple_tag
def oven_icon_styles() -> str:
    """The chart chips' symbols, as CSS masks; see recipes.oven."""
    return mark_safe(oven_mask_css())  # noqa: S308
