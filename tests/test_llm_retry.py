"""
Tests for LLM retry logic (Task 11: exponential backoff) and
chunk LLM call cap (Task 16: MAX_LLM_CALLS_PER_CHUNK).
"""
import sys
from unittest.mock import patch, MagicMock
import pytest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestCompleteRetries:
    """Test exponential backoff in LLMService.complete()."""

    def _make_service(self):
        from src.utils import LLMService, LLMRole
        svc = LLMService()
        return svc, LLMRole

    def _mock_config(self):
        mock_cfg = MagicMock()
        mock_cfg.debug = False
        mock_cfg.sys_not_promt_translate = False
        mock_cfg.sys_not_promt_proofread = False
        mock_cfg.disable_json_mode_translate = False
        mock_cfg.disable_json_mode_proofread = False
        mock_cfg.nothink_translate = False
        mock_cfg.nothink_proofread = False
        mock_cfg.temp_translate = 0.3
        mock_cfg.temp_proofread = 0.2
        return mock_cfg

    @patch("time.sleep")
    def test_complete_retries_on_error(self, mock_sleep):
        """Mock API to fail twice then succeed → assert 3 calls made."""
        svc, LLMRole = self._make_service()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello world"
        mock_response.choices[0].message.reasoning = None
        mock_response.model = "test-model"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("Connection error"),
            Exception("Rate limit 429"),
            mock_response,
        ]

        with patch.object(svc, 'get_client', return_value=(mock_client, "test-model", 0.3)), \
             patch("src.utils.config", self._mock_config()):

            result = svc.complete(
                role=LLMRole.TRANSLATE,
                system_prompt="You are a translator.",
                user_prompt="Translate: Hello",
                track_tokens=False,
                allow_empty=True,
            )

        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    def test_complete_raises_after_max_retries(self, mock_sleep):
        """Mock API to always fail → assert raises after 3 attempts."""
        svc, LLMRole = self._make_service()

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Server error 500")

        with patch.object(svc, 'get_client', return_value=(mock_client, "test-model", 0.3)), \
             patch("src.utils.config", self._mock_config()):

            with pytest.raises(Exception, match="Server error 500"):
                svc.complete(
                    role=LLMRole.TRANSLATE,
                    system_prompt="You are a translator.",
                    user_prompt="Translate: Hello",
                    track_tokens=False,
                    allow_empty=True,
                )

        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2


class TestChunkCallCap:
    """Test MAX_LLM_CALLS_PER_CHUNK cap in translate_chunk."""

    @patch("src.utils._pipeline")
    def test_chunk_cap_stops_recursion(self, mock_pipeline):
        """Mock pipeline to always return empty → assert stops at MAX_LLM_CALLS_PER_CHUNK."""
        from src.utils import translate_chunk, MAX_LLM_CALLS_PER_CHUNK

        # Mock pipeline.execute to return a state with empty translation
        mock_state = MagicMock()
        mock_state.final_translation = ""
        mock_state.synopsis = ""
        mock_state.final_result = MagicMock()
        mock_state.final_result.tokens_used = 0
        mock_pipeline.execute.return_value = mock_state

        with patch("src.utils.validate_translation_length", return_value=(False, 0.0, False)), \
             patch("src.utils.config") as mock_config, \
             patch("src.utils.metrics") as mock_metrics:
            mock_config.debug = False
            mock_metrics.log_failure = MagicMock()
            mock_metrics.log_success = MagicMock()

            result, synopsis = translate_chunk(
                source_lang="en",
                target_lang="ru",
                source_text="Hello world " * 100,
                outline_text="",
                vocab_dict={},
            )

        # Pipeline should be called at most MAX_LLM_CALLS_PER_CHUNK times
        assert mock_pipeline.execute.call_count <= MAX_LLM_CALLS_PER_CHUNK
        assert result == ""
        assert synopsis == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
