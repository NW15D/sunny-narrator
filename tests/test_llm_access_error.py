"""
An API that refuses the request itself - the key (401), the access (403), the
model (404) - stops the run at once (LLMAccessError): no retry, no split of the
chunk, no "keeping the original" chunk after chunk. A clean cloud install with
a blocked network did all of that through the whole book.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
from src import utils
from src.utils import LLMAccessError, LLMRole


def _error(cls, status, body):
    response = httpx.Response(status, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return cls(str(body), response=response, body=body)


@pytest.mark.parametrize("cls, status, hint", [
    (openai.AuthenticationError, 401, "API_KEY_TRANSLATE"),
    (openai.PermissionDeniedError, 403, "ProxyAPI"),
    (openai.NotFoundError, 404, "MODEL_TRANSLATE"),
])
def test_a_refused_request_is_not_retried(cls, status, hint):
    client = MagicMock()
    client.base_url = "https://openrouter.ai/api/v1"
    client.chat.completions.create.side_effect = _error(cls, status, {"error": "Access denied by security policy."})
    svc = utils.LLMService()
    with patch.object(svc, 'get_client', return_value=(client, "google/gemma-4-26b-a4b-it", 0.1)), \
            patch("time.sleep") as sleep:
        with pytest.raises(LLMAccessError, match=hint) as raised:
            svc.complete(role=LLMRole.TRANSLATE, system_prompt="S", user_prompt="U", allow_empty=True)
    assert client.chat.completions.create.call_count == 1 and sleep.call_count == 0
    assert "google/gemma-4-26b-a4b-it" in str(raised.value) and "openrouter.ai" in str(raised.value)


def test_translate_chunk_does_not_split_on_it(monkeypatch):
    calls = []

    def execute(**kw):
        calls.append(kw['source_text'])
        raise LLMAccessError("the translate LLM refused the request")

    monkeypatch.setattr(utils._pipeline, 'execute', execute)
    with pytest.raises(LLMAccessError):
        utils.translate_chunk("english", "russian", "One. Two.\n\nThree. Four.", "", {}, [], "Россия")
    assert len(calls) == 1, "halves of the chunk would be refused the same way"


def test_the_calibre_run_stops_at_the_first_chunk(tmp_path, monkeypatch):
    book = tmp_path / "book.epub"
    book.write_bytes(b"fake")
    calls = []

    def refused(**kw):
        calls.append(kw['source_text'])
        raise LLMAccessError("the translate LLM refused the request")

    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda text, size: ["One.", "Two.", "Three."])
    monkeypatch.setattr(cp.config, 'ner_opt', False)
    monkeypatch.setattr(cp.config, 'dictionary', None)
    with patch.object(cp, 'translate_chunk', side_effect=refused), patch("time.sleep"):
        with pytest.raises(LLMAccessError):
            cp.translate_chunks("ignored", book_path=str(book))
    assert calls == ["One."]


def test_metadata_translation_lets_it_through(monkeypatch):
    def refused(**kw):
        raise LLMAccessError("the proofread LLM refused the request")

    monkeypatch.setattr(utils.llm_service_compat, 'get_completion', refused)
    with pytest.raises(LLMAccessError):
        utils.translate_metadata({"title": "T"}, "english", "russian", "Россия")
