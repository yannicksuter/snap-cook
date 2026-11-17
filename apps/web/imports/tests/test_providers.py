# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Anthropic adapter's request, and how its failures reach a reader.

The client is a stand-in that records the call: no request leaves the machine,
and no test spends money. What is checked is the shape the adapter sends --
model, effort, schema, cached instructions, attachments -- and that every way
a call can end is turned into something the pipeline expects.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from imports.providers import NotSetUp, ProviderError, importer
from imports.providers.anthropic import AnthropicImporter
from imports.providers.fake import FakeImporter
from snapcook_core.importing import ImportFile, ImportSource, RawExtraction, system_prompt
from snapcook_core.translating import (
    Piece,
    RawTranslation,
    TranslatedPiece,
    TranslationRequest,
    translation_prompt,
)

_READING = RawExtraction(is_recipe=True, cooklang="---\ntitle: Soup\n---\n\nStir @water{1%l}.")


class _Messages:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _response(stop_reason: str = "end_turn", parsed=_READING):
    usage = SimpleNamespace(input_tokens=1200, cache_read_input_tokens=0, output_tokens=300)
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        model="claude-opus-5-5",
        usage=usage,
        _request_id="req_test",
    )


def _importer(outcome=None, *, model: str = "claude-opus-5-5", effort: str = "medium"):
    messages = _Messages(_response() if outcome is None else outcome)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return AnthropicImporter(api_key="sk-test", model=model, effort=effort, client=client), messages


def _status_error(cls, status: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("no", response=httpx2.Response(status, request=request), body=None)


def test_the_request_asks_for_a_raw_extraction() -> None:
    reader, messages = _importer()
    assert reader.extract(ImportSource(kind="text", text="Soup: stir water.")) == _READING

    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is RawExtraction
    assert call["output_config"] == {"effort": "medium"}
    assert call["system"] == [
        {"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}
    ]
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    (content,) = call["messages"]
    assert content["role"] == "user"
    assert content["content"][-1]["type"] == "text"
    assert "Soup: stir water." in content["content"][-1]["text"]


def test_photos_go_first_and_pdfs_as_documents() -> None:
    reader, messages = _importer()
    files = (
        ImportFile(b"\xff\xd8\xffjpeg", "image/jpeg"),
        ImportFile(b"%PDF-1.7", "application/pdf"),
    )
    reader.extract(ImportSource(kind="files", files=files))

    photo, pdf, text = messages.calls[0]["messages"][0]["content"]
    assert photo["type"] == "image"
    assert photo["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": base64.standard_b64encode(b"\xff\xd8\xffjpeg").decode(),
    }
    assert pdf["type"] == "document"
    assert pdf["source"]["media_type"] == "application/pdf"
    assert text["type"] == "text"


def test_a_model_without_fallbacks_is_asked_without_them() -> None:
    reader, messages = _importer(model="claude-haiku-5-5")
    reader.extract(ImportSource(kind="text", text="x"))
    assert "fallbacks" not in messages.calls[0]
    assert "betas" not in messages.calls[0]


def test_an_unknown_effort_falls_back_to_medium() -> None:
    reader, messages = _importer(effort="extreme")
    reader.extract(ImportSource(kind="text", text="x"))
    assert messages.calls[0]["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize(
    ("stop_reason", "parsed", "code"),
    [
        ("refusal", None, "refused"),
        ("max_tokens", None, "model_failed"),
        ("end_turn", None, "model_failed"),
    ],
)
def test_an_answer_without_a_reading_is_a_provider_error(stop_reason, parsed, code) -> None:
    reader, _ = _importer(_response(stop_reason, parsed))
    with pytest.raises(ProviderError) as failed:
        reader.extract(ImportSource(kind="text", text="x"))
    assert failed.value.code == code


def test_a_refused_key_means_not_set_up() -> None:
    reader, _ = _importer(_status_error(anthropic.AuthenticationError, 401))
    with pytest.raises(NotSetUp):
        reader.extract(ImportSource(kind="text", text="x"))


@pytest.mark.parametrize(
    ("error", "code"),
    [(anthropic.RateLimitError, "busy"), (anthropic.InternalServerError, "model_failed")],
)
def test_api_errors_become_provider_errors(error, code) -> None:
    status = 429 if error is anthropic.RateLimitError else 500
    reader, _ = _importer(_status_error(error, status))
    with pytest.raises(ProviderError) as failed:
        reader.extract(ImportSource(kind="text", text="x"))
    assert failed.value.code == code


def test_without_a_key_nothing_is_set_up(settings) -> None:
    settings.SNAPCOOK_LLM_PROVIDER = "anthropic"
    settings.SNAPCOOK_LLM_API_KEY = ""
    with pytest.raises(NotSetUp):
        importer()


def test_with_a_key_the_anthropic_reader_is_used(settings) -> None:
    settings.SNAPCOOK_LLM_PROVIDER = "anthropic"
    settings.SNAPCOOK_LLM_API_KEY = "sk-test"
    assert isinstance(importer(), AnthropicImporter)


@pytest.mark.parametrize(("provider", "available"), [("fake", True), ("local", False), ("", False)])
def test_other_providers(settings, provider: str, available: bool) -> None:
    settings.SNAPCOOK_LLM_PROVIDER = provider
    if available:
        assert isinstance(importer(), FakeImporter)
    else:
        with pytest.raises(NotSetUp):
            importer()


def test_a_translation_asks_for_every_piece_at_low_effort() -> None:
    answer = RawTranslation(pieces=[TranslatedPiece(key="title", text="Cheesecake")])
    reader, messages = _importer(_response(parsed=answer))
    request = TranslationRequest("de", "en", (Piece("title", "Käsekuchen", "the recipe's name"),))
    assert reader.translate(request) == answer

    call = messages.calls[0]
    assert call["output_format"] is RawTranslation
    assert call["output_config"] == {"effort": "low"}
    assert call["system"][0]["text"] == translation_prompt("de", "en")
    (content,) = call["messages"]
    assert '"text": "Käsekuchen"' in content["content"][0]["text"]


def test_the_fake_translation_keeps_every_slot() -> None:
    request = TranslationRequest("de", "en", (Piece("step:a", "Die ⟦1⟧ rühren."),))
    (piece,) = FakeImporter().translate(request).pieces
    assert piece.text == "[en] Die ⟦1⟧ rühren."
