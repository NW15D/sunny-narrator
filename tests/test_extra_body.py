"""
The request fields the OpenAI SDK has no argument for (utils._extra_body):
thinking is off by default for both a llama.cpp server (chat_template_kwargs)
and a hosted API such as OpenRouter or ProxyAPI (reasoning.effort), and
EXTRA_BODY_* is merged into every request of its model.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import config as config_module
from src import utils
from src.utils import LLMRole


def test_thinking_is_off_by_default(monkeypatch):
    for name in ('NOTHINK_TRANSLATE', 'NOTHINK_PROOFREAD', 'NOTHINK'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, 'load_dotenv', lambda *a, **kw: None)
    cfg = config_module.Config()
    assert cfg.nothink_translate and cfg.nothink_proofread


def test_nothink_turns_thinking_off_on_local_and_hosted_servers(monkeypatch):
    monkeypatch.setattr(utils.config, 'nothink_translate', True)
    monkeypatch.setattr(utils.config, 'extra_body_translate', {})
    assert utils._extra_body(LLMRole.TRANSLATE) == {
        "chat_template_kwargs": {"enable_thinking": False}, "reasoning": {"effort": "none"}}


def test_extra_body_is_merged_and_thinking_left_alone_when_asked(monkeypatch):
    provider = {"provider": {"require_parameters": True, "quantizations": ["bf16", "fp8"]}}
    monkeypatch.setattr(utils.config, 'nothink_proofread', False)
    monkeypatch.setattr(utils.config, 'extra_body_proofread', provider)
    assert utils._extra_body(LLMRole.PROOFREAD) == provider
    monkeypatch.setattr(utils.config, 'nothink_proofread', True)
    body = utils._extra_body(LLMRole.PROOFREAD)
    assert body["provider"] == provider["provider"] and body["reasoning"] == {"effort": "none"}
    assert provider == {"provider": {"require_parameters": True, "quantizations": ["bf16", "fp8"]}}, \
        "the configured object is not changed"


def test_extra_body_must_be_a_json_object(monkeypatch):
    monkeypatch.setenv('EXTRA_BODY_PROOFREAD', '{"provider": ')
    with pytest.raises(ValueError, match="EXTRA_BODY_PROOFREAD is not valid JSON"):
        config_module._parse_json_env('EXTRA_BODY_PROOFREAD')
    monkeypatch.setenv('EXTRA_BODY_PROOFREAD', '[1, 2]')
    with pytest.raises(ValueError, match="must be a JSON object"):
        config_module._parse_json_env('EXTRA_BODY_PROOFREAD')
    monkeypatch.delenv('EXTRA_BODY_PROOFREAD')
    assert config_module._parse_json_env('EXTRA_BODY_PROOFREAD') == {}
