"""C1/C4: rechunk must fail the chunk when a half is empty, not merge partials."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_rechunk_half_failure_fails_chunk(monkeypatch):
    import src.utils as u

    calls = {'exec': 0, 'val': 0}

    def fake_execute(**kwargs):
        calls['exec'] += 1
        # First call: non-empty draft; all subsequent: empty (LLM failure)
        text = 'DRAFT' if calls['exec'] == 1 else ''
        return SimpleNamespace(final_translation=text, synopsis='', final_result=None)

    def fake_validate(source_text, translated_text, stage_name=''):
        calls['val'] += 1
        if calls['val'] == 1:
            return False, 90.0, True  # first check: needs split
        return True, 0.0, False

    monkeypatch.setattr(u._pipeline, 'execute', fake_execute)
    monkeypatch.setattr(u, 'validate_translation_length', fake_validate)

    source = ('First sentence here. Second sentence here. Third sentence here. '
              'Fourth sentence here. Fifth sentence here.')
    result, synopsis = u.translate_chunk(
        'en', 'ru', source, '', {}, [], '', 'text', False
    )
    # Fail-fast: empty half must fail the whole chunk, not produce "\n\n"
    assert result == ''
