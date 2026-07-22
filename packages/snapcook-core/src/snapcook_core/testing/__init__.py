# SPDX-License-Identifier: Apache-2.0
"""Shared test and seed fixtures.

The corpus and its builders live in the shipped package rather than the test
tree because they are product artifacts: a seed script, a CLI and the golden
tests all want the same six recipes, built the same way.
"""

from snapcook_core.testing.builders import Chef
from snapcook_core.testing.corpus import CORPUS, corpus_recipes, get_recipe

__all__ = ["CORPUS", "Chef", "corpus_recipes", "get_recipe"]
