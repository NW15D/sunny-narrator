"""C5: no-op repair step removed; repair_xml must not lose content on truncated prompts."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_remove_duplicate_closings_removed():
    from src import fb2_repair
    assert not hasattr(fb2_repair, '_remove_duplicate_closings')


def test_repair_xml_refuses_short_result_on_truncated_input(monkeypatch):
    import src.xml_post_processor as xpp

    proc = xpp.XmlPostProcessor.__new__(xpp.XmlPostProcessor)
    proc.config = SimpleNamespace(source_lang='en', target_lang='ru',
                                  model_proofread='test-model',
                                  llm_repair_max_tokens=2000)

    fake_choice = MagicMock()
    fake_choice.message.content = 'short result'
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = SimpleNamespace(choices=[fake_choice])

    monkeypatch.setattr(xpp.ta, 'llm_service',
                        SimpleNamespace(clientProofread=fake_client))

    long_source = 'x' * 1500
    long_translation = 'y' * 1500
    result = proc.repair_xml(long_source, long_translation)
    # Truncated prompt cannot restore the full text — original must be kept.
    assert result == long_translation
