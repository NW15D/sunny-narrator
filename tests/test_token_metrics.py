"""E4 (audit F6): translate_chunk must log token usage from PipelineState.total_tokens."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.utils as utils


def test_translate_chunk_logs_tokens_from_state(monkeypatch):
    state = utils.PipelineState(context=None)
    state.total_tokens = 123
    state.final_translation = "Тестовый перевод"
    state.synopsis = "Тестовый синопсис"

    monkeypatch.setattr(utils._pipeline, "execute", lambda **kwargs: state)
    monkeypatch.setattr(
        utils, "validate_translation_length",
        lambda source, translation, stage: (True, 0.0, False)
    )

    before = utils.metrics.get_report()["total_tokens"]
    translation, synopsis = utils.translate_chunk(
        "English", "Russian", "Some source text long enough to pass.",
        "", {}, fast_mode=True
    )

    assert translation == "Тестовый перевод"
    assert synopsis == "Тестовый синопсис"
    assert utils.metrics.get_report()["total_tokens"] - before == 123
