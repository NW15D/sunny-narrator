"""Fixes of the cloud review of 2026-10-19: strict servers, moderation 403,
a list cut at a line break, a closed but invalid JSON answer, dict convert."""
import os
import sys
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import dict_convert, utils
from src.utils import LLMAccessError, LLMRole


def _error(cls, status, message):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"))
    return cls(message, response=response, body={"error": message})


def _complete(client, role=LLMRole.TRANSLATE):
    svc = utils.LLMService()
    with patch.object(svc, 'get_client', return_value=(client, "m", 0.1)), patch("time.sleep"):
        return svc.complete(role=role, system_prompt="S", user_prompt="U", allow_empty=True)


@pytest.fixture(autouse=True)
def _forget_rejected_fields():
    utils._rejected_fields.clear()
    yield
    utils._rejected_fields.clear()


def _ok():
    reply = MagicMock()
    reply.choices[0].message.content = "ok"
    reply.choices[0].finish_reason = "stop"
    reply.usage.total_tokens = reply.usage.prompt_tokens = reply.usage.completion_tokens = 1
    return reply


def test_a_strict_server_gets_the_request_without_the_extra_fields(monkeypatch):
    monkeypatch.setattr(utils.config, 'nothink_translate', True)
    client = MagicMock()
    client.base_url = "https://api.example.com/v1"
    client.chat.completions.create.side_effect = [
        _error(openai.BadRequestError, 400, "Unrecognized request argument supplied: chat_template_kwargs"),
        _ok(), _ok()]
    _complete(client)
    first, second = (c.kwargs for c in client.chat.completions.create.call_args_list)
    assert "chat_template_kwargs" in first["extra_body"] and "presence_penalty" in first
    assert "extra_body" not in second
    assert utils._rejected_fields["translate"] == {"chat_template_kwargs", "reasoning", "presence_penalty"}
    assert "presence_penalty" not in second
    # the next request of the role does not send them at all
    _complete(client)
    assert "extra_body" not in client.chat.completions.create.call_args_list[-1].kwargs


def test_an_ordinary_400_is_still_retried_as_before():
    client = MagicMock()
    client.base_url = "https://api.example.com/v1"
    client.chat.completions.create.side_effect = [
        _error(openai.BadRequestError, 400, "context length exceeded"), _ok()]
    _complete(client)
    assert client.chat.completions.create.call_count == 2
    assert not utils._rejected_fields


def test_a_moderation_403_is_the_chunks_not_the_keys():
    client = MagicMock()
    client.base_url = "https://openrouter.ai/api/v1"
    client.chat.completions.create.side_effect = _error(
        openai.PermissionDeniedError, 403, "Your chosen model requires moderation and your input was flagged")
    with pytest.raises(openai.PermissionDeniedError):
        _complete(client)
    assert client.chat.completions.create.call_count == 3  # retried, not LLMAccessError


def test_any_other_403_still_stops_the_run():
    client = MagicMock()
    client.base_url = "https://openrouter.ai/api/v1"
    client.chat.completions.create.side_effect = _error(
        openai.PermissionDeniedError, 403, "Access denied by security policy.")
    with pytest.raises(LLMAccessError):
        _complete(client)
    assert client.chat.completions.create.call_count == 1


def test_a_list_cut_at_a_line_break_stays_a_list():
    part1 = "- He left.\n- She stayed.\n"
    join = utils._join_text_halves(part1)
    assert join("- Он ушёл.\n- Она осталась.", "- Они спорили.") == "- Он ушёл.\n- Она осталась.\n- Они спорили."
    assert utils._join_text_halves("A paragraph.\n\n") is None
    assert utils._join_text_halves("One sentence. ")("Раз.", "Два.") == "Раз. Два."


def test_a_closed_answer_with_an_unescaped_quote_is_recovered_not_truncated():
    text = '{"translation": "Она сказала: "Иди."}'
    assert not utils._unclosed_json_answer(text)
    assert utils.remove_tags_with_check(text, "initial") == 'Она сказала: "Иди.'
    assert utils._unclosed_json_answer('{"translation": "Она сказала: "Иди.')


def test_dict_convert_never_writes_over_its_source(tmp_path):
    src = tmp_path / "book_ru.dic"
    src.write_text("a = b,PERSON,,\n", encoding="utf-8")
    client = MagicMock()
    assert dict_convert.convert(src, "ru", 40, True, client, "english", "russian") is True
    client.chat.completions.create.assert_not_called()
    assert src.read_text(encoding="utf-8") == "a = b,PERSON,,\n"
