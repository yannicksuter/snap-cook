# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read recipes with Claude through the Anthropic API.

One request per import: the instructions (identical every time, so they are
cached), the source -- photos and PDFs as attachments, a page or pasted text as
text -- and ``RawExtraction`` as the required output shape. The model's answer is
validated against that schema by the SDK and then handed to core's
``normalize``, which trusts none of it.

The request runs on the worker (``imports.tasks``), never in a web request. Its
time limits are set so the SDK's own retries finish well inside the worker's
300-second task timeout: a job killed by the worker would sit in "reading"
until someone notices.
"""

from __future__ import annotations

import base64
import logging

import anthropic

from imports.providers import NotSetUp, ProviderError
from snapcook_core.importing import ImportSource, RawExtraction, describe_source, system_prompt

__all__ = ["AnthropicImporter"]

logger = logging.getLogger(__name__)

_MAX_TOKENS = 16_000
_TIMEOUT = 120.0
_RETRIES = 1
_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Models that take server-side refusal fallbacks: a declined request is re-run on
# a fallback model inside the same call rather than failing the import.
_FALLBACK_MODELS = frozenset(
    {
        "claude-fable-5-2",
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    }
)


class AnthropicImporter:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: str = "medium",
        base_url: str | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._model = model
        self._effort = effort if effort in _EFFORTS else "medium"
        self._client = client or anthropic.Anthropic(
            api_key=api_key, base_url=base_url, timeout=_TIMEOUT, max_retries=_RETRIES
        )

    def extract(self, source: ImportSource) -> RawExtraction:
        fallback = {}
        if self._model in _FALLBACK_MODELS:
            fallback = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt(),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": _content(source)}],
                output_format=RawExtraction,
                output_config={"effort": self._effort},
                **fallback,
            )
        except anthropic.AuthenticationError as error:
            raise NotSetUp("the API key was refused") from error
        except anthropic.PermissionDeniedError as error:
            raise NotSetUp("the API key may not use this model") from error
        except anthropic.BadRequestError as error:
            raise ProviderError("model_failed", f"request rejected: {error.message}") from error
        except anthropic.RateLimitError as error:
            raise ProviderError("busy", "rate limited; try again later") from error
        except anthropic.APIStatusError as error:
            raise ProviderError("model_failed", f"API error {error.status_code}") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError("model_failed", "could not reach the API") from error

        usage = response.usage
        logger.info(
            "import read by %s: %s input, %s cached, %s output tokens, stop %s, request %s",
            response.model,
            usage.input_tokens,
            usage.cache_read_input_tokens,
            usage.output_tokens,
            response.stop_reason,
            response._request_id,
        )
        if response.stop_reason == "refusal":
            raise ProviderError("refused", "the model declined to read this source")
        if response.stop_reason == "max_tokens":
            raise ProviderError("model_failed", "the reading was cut off before it finished")
        if response.parsed_output is None:
            raise ProviderError("model_failed", "the answer did not match the expected shape")
        return response.parsed_output


def _content(source: ImportSource) -> list[dict]:
    """Attachments first, then the text that says what they are."""
    blocks: list[dict] = []
    for file in source.files:
        data = base64.standard_b64encode(file.data).decode("ascii")
        kind = "document" if file.media_type == "application/pdf" else "image"
        blocks.append(
            {
                "type": kind,
                "source": {"type": "base64", "media_type": file.media_type, "data": data},
            }
        )
    blocks.append({"type": "text", "text": describe_source(source)})
    return blocks
