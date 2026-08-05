"""A6: empty translation result must count as failure, not success."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app as app_module
from app import TranslationEngine


def _make_engine():
    eng = TranslationEngine.__new__(TranslationEngine)
    eng.stats = {'successful': 0, 'failed': 0, 'retry_tokens': 0, 'total_tokens': 0}
    return eng


def test_empty_translation_counts_as_failure():
    eng = _make_engine()
    eng.translate_chunk = MagicMock(return_value=("Some text", ""))
    eng._post_process_xml = MagicMock(return_value="   ")
    with patch.object(app_module, 'ta') as mock_ta:
        mock_ta.num_tokens_in_string.return_value = 1
        result, _synopsis = eng.process_chunk_recursive("<p>Hello</p>", 0, 0, 1, "")
    assert eng.stats['successful'] == 0
    assert eng.stats['failed'] == 1
    assert "FAILED" in result
