"""Tests for config.py fixes: hardcoded API key removal and bool env parsing."""
import os
import pytest
from unittest.mock import patch


@pytest.fixture
def clean_env():
    """Remove all config-related env vars to test defaults."""
    keys_to_clear = [
        'API_KEY_TRANSLATE', 'API_KEY', 'API_KEY_PROOFREAD', 'API_KEY2',
        'S_PROMT_TRANSLATE', 'S_PROMT', 'S_PROMT_PROOFREAD', 'S_PROMT2',
        'S_PROMT_IMAGES', 'S_PROMT3',
    ]
    with patch.dict(os.environ, {}, clear=False):
        for k in keys_to_clear:
            os.environ.pop(k, None)
        yield


class TestNoHardcodedKey:
    """Bug 1: API keys must not have hardcoded UUID fallbacks."""

    def test_no_hardcoded_key_translate(self, clean_env):
        from src.config import Config
        cfg = Config(env_path="/dev/null")  # skip .env loading
        assert cfg.api_key_translate == ""
        assert cfg.api_key_translate != "a132b20c-96be-467f-a15a-ed08aed67345"

    def test_no_hardcoded_key_proofread(self, clean_env):
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.api_key_proofread == ""
        assert cfg.api_key_proofread != "a132b20c-96be-467f-a15a-ed08aed67345"


class TestBoolEnvParsing:
    """Bug 2: bool(os.getenv(...)) must correctly parse 'false'/'0' as False."""

    def test_bool_env_false(self, clean_env):
        """S_PROMT_TRANSLATE='false' should be False, not True."""
        os.environ['S_PROMT_TRANSLATE'] = 'false'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is False

    def test_bool_env_zero(self, clean_env):
        """S_PROMT_TRANSLATE='0' should be False."""
        os.environ['S_PROMT_TRANSLATE'] = '0'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is False

    def test_bool_env_true(self, clean_env):
        """S_PROMT_TRANSLATE='true' should be True."""
        os.environ['S_PROMT_TRANSLATE'] = 'true'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is True

    def test_bool_env_one(self, clean_env):
        """S_PROMT_TRANSLATE='1' should be True."""
        os.environ['S_PROMT_TRANSLATE'] = '1'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is True

    def test_bool_env_on(self, clean_env):
        """S_PROMT_TRANSLATE='on' should be True."""
        os.environ['S_PROMT_TRANSLATE'] = 'on'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is True

    def test_bool_env_unset_is_false(self, clean_env):
        """When S_PROMT_TRANSLATE is not set, default should be False."""
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is False

    def test_bool_env_empty_is_false(self, clean_env):
        """S_PROMT_TRANSLATE='' should be False."""
        os.environ['S_PROMT_TRANSLATE'] = ''
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_translate is False

    def test_bool_proofread_false(self, clean_env):
        """S_PROMT_PROOFREAD='false' should be False."""
        os.environ['S_PROMT_PROOFREAD'] = 'false'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_proofread is False

    def test_bool_images_false(self, clean_env):
        """S_PROMT_IMAGES='0' should be False."""
        os.environ['S_PROMT_IMAGES'] = '0'
        from src.config import Config
        cfg = Config(env_path="/dev/null")
        assert cfg.sys_not_promt_images is False
