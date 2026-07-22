# SPDX-License-Identifier: Apache-2.0
"""Cooklang-flavoured authoring: parse in, print out.

An input and export format, never the stored source of truth -- one mutable
representation, not two. The printer and parser are inverses over snap-cook's
canonical dialect, and ``print(parse(text)) == text`` is the gate that keeps them
honest (``tests/property/test_cooklang_roundtrip.py``).
"""

from snapcook_core.cooklang.parse import parse_cook
from snapcook_core.cooklang.print_ import print_cook

__all__ = ["parse_cook", "print_cook"]
