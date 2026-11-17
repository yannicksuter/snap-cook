# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which model reads and translates recipes here, chosen by ``SNAPCOOK_LLM_PROVIDER``.

Every provider satisfies ``snapcook_core.importing.RecipeImporter`` and
``snapcook_core.translating.RecipeTranslator``. The rest of the app sees only
those protocols, so a local model can replace the hosted one later without
anything else changing.
"""

from __future__ import annotations

from django.conf import settings

from snapcook_core.importing import RecipeImporter
from snapcook_core.translating import RecipeTranslator

__all__ = ["NotSetUp", "ProviderError", "importer", "is_set_up", "translator"]


class NotSetUp(Exception):
    """This server has no usable provider: no key, or a provider not built yet."""


class ProviderError(Exception):
    """The model was asked and did not deliver. ``code`` is shown to readers."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def is_set_up() -> bool:
    try:
        importer()
    except NotSetUp:
        return False
    return True


def importer() -> RecipeImporter:
    """The configured provider. Cheap: constructing one makes no request."""
    return _provider()


def translator() -> RecipeTranslator:
    """The same provider, for translating. Raises ``NotSetUp`` the same way."""
    return _provider()


def _provider():
    provider = settings.SNAPCOOK_LLM_PROVIDER
    if provider == "anthropic":
        if not settings.SNAPCOOK_LLM_API_KEY:
            raise NotSetUp("SNAPCOOK_LLM_API_KEY is not set")
        from imports.providers.anthropic import AnthropicImporter

        return AnthropicImporter(
            api_key=settings.SNAPCOOK_LLM_API_KEY,
            model=settings.SNAPCOOK_LLM_MODEL,
            effort=settings.SNAPCOOK_LLM_EFFORT,
            base_url=settings.SNAPCOOK_LLM_BASE_URL or None,
        )
    if provider == "fake":
        from imports.providers.fake import FakeImporter

        return FakeImporter()
    raise NotSetUp(f"provider {provider!r} is not available")
