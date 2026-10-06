"""A failed chunk (e.g. response cut off by max_tokens) is translated as two halves."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SOURCE = ('First sentence here. Second sentence here. Third sentence here.\n\n'
          'Fourth sentence here. Fifth sentence here. Sixth sentence here.')


def _patch(monkeypatch, limit, kind='trunc'):
    import src.utils as u
    sizes = []

    def fake_execute(**kw):
        text = kw['source_text']
        sizes.append(len(text))
        if len(text) > limit:
            raise (u.TruncatedResponseError("LLM response was truncated") if kind == 'trunc'
                   else RuntimeError("bad response"))
        return SimpleNamespace(final_translation='T:' + text, synopsis='s',
                               synopsis_candidates=[], total_tokens=0)

    monkeypatch.setattr(u._pipeline, 'execute', fake_execute)
    monkeypatch.setattr(u, 'validate_translation_length',
                        lambda *a, **k: (True, 0.0, False))
    return u, sizes


def test_truncated_chunk_is_split_and_joined(monkeypatch):
    u, sizes = _patch(monkeypatch, limit=len(SOURCE) - 10)
    result, _ = u.translate_chunk('en', 'ru', SOURCE, '', {}, [], '', 'text', False)
    assert result.count('T:') == 2
    assert 'First' in result and 'Sixth' in result
    assert sizes[0] == len(SOURCE) and len(sizes) == 3


def test_truncation_gives_up_when_halves_still_truncate(monkeypatch):
    u, _ = _patch(monkeypatch, limit=0)
    with pytest.raises(u.TruncatedResponseError):
        u.translate_chunk('en', 'ru', SOURCE, '', {}, [], '', 'text', False)


def test_any_error_splits_the_chunk(monkeypatch):
    u, sizes = _patch(monkeypatch, limit=len(SOURCE) - 10, kind='other')
    result, _ = u.translate_chunk('en', 'ru', SOURCE, '', {}, [], '', 'text', False)
    assert result.count('T:') == 2


def test_pipeline_abort_is_not_split(monkeypatch):
    import src.utils as u
    from src.stage_pipeline import PipelineAborted
    calls = []

    def fake_execute(**kw):
        calls.append(kw['source_text'])
        raise PipelineAborted("neighbour failed")

    monkeypatch.setattr(u._pipeline, 'execute', fake_execute)
    with pytest.raises(PipelineAborted):
        u.translate_chunk('en', 'ru', SOURCE, '', {}, [], '', 'text', False)
    assert len(calls) == 1


def test_empty_half_reraises_original_error(monkeypatch):
    import src.utils as u
    monkeypatch.setattr(u, 'MAX_LLM_CALLS_PER_CHUNK', 2)  # second half hits the cap
    _patch(monkeypatch, limit=len(SOURCE) - 10, kind='other')
    with pytest.raises(RuntimeError, match="bad response"):
        u.translate_chunk('en', 'ru', SOURCE, '', {}, [], '', 'text', False)
