"""B9/C12: complete() must raise when the LLM response is truncated."""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


def test_complete_raises_on_truncated_response(monkeypatch):
    import src.utils as u

    svc = u.LLMService()

    fake_choice = MagicMock()
    fake_choice.finish_reason = 'length'
    fake_choice.message.content = 'partial text'
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]
    fake_resp.usage = None
    fake_resp.model = 'test-model'
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp

    monkeypatch.setattr(svc, 'get_client', lambda role: (fake_client, 'test-model', 0.1))

    with pytest.raises(ValueError, match='truncated'):
        svc.complete(u.LLMRole.TRANSLATE, 'sys', 'user', max_tokens=16, track_tokens=False)
