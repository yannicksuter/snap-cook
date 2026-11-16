# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which model reads recipes on this server, chosen by ``SNAPCOOK_LLM_PROVIDER``.

Every provider satisfies ``snapcook_core.importing.RecipeImporter``. The rest of
the pipeline sees only that protocol, so a local model can replace the hosted
one later without anything else changing.
"""

from __future__ import annotations

from django.conf import settings

from snapcook_core.importing import RecipeImporter

__all__ = ["NotSetUp", "ProviderError", "importer", "is_set_up"]


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
