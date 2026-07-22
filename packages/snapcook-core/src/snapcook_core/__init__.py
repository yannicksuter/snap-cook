# SPDX-License-Identifier: Apache-2.0
"""snapcook-core -- the structured recipe domain model.

A recipe is a directed acyclic graph whose nodes are *food-states* ("the dough",
"the roux") and whose edges are *actions* carrying a verb, duration,
temperature and tools. Everything a reader sees -- an ordered step list, a
flowchart, a printed page -- is a rendering of that graph, not a separate
representation of it.

This package never imports Django. It is the shared brain for the web app, a
future Flutter client, a CLI and a self-hosted LLM service.
"""

from snapcook_core.version import FORMAT_VERSION, HASH_ALGO_PREFIX, LIB_VERSION

__all__ = ["FORMAT_VERSION", "HASH_ALGO_PREFIX", "LIB_VERSION"]
__version__ = LIB_VERSION
