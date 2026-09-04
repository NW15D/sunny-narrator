"""D5: calibre translate_chunks saves per-chunk checkpoints and resumes."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import src.calibre_pipeline as cp


class _FakeState:
    def __init__(self, text):
        self.final_translation = text
        self.synopsis = ''
        # translate_chunk reads state.total_tokens on the success path
        # (src/utils.py). Without it every "translation" raised AttributeError,
        # was retried three times, and the resume assertions below failed for a
        # reason that had nothing to do with checkpoints.
        self.total_tokens = 0


def _install(monkeypatch, calls, crash_after=None):
    def fake_execute(**kwargs):
        if crash_after is not None and len(calls) >= crash_after:
            raise KeyboardInterrupt()
        calls.append(kwargs['source_text'])
        return _FakeState('TR:' + kwargs['source_text'])

    monkeypatch.setattr(cp._pipeline, 'execute', fake_execute)
    monkeypatch.setattr(cp, 'validate_translation_length',
                        lambda src, dst, label: (True, 0.0, False))
    monkeypatch.setattr(cp, '_split_into_chunks_md',
                        lambda text, size: [p for p in text.split('\n\n') if p])


def test_checkpoint_resume_skips_done_chunks(tmp_path, monkeypatch):
    calls = []
    _install(monkeypatch, calls, crash_after=2)

    ckpt = str(tmp_path / 'book.checkpoint.json')
    text = 'AAA\n\nBBB\n\nCCC\n\nDDD'

    # Run 1: "crash" after two chunks
    with pytest.raises(KeyboardInterrupt):
        cp.translate_chunks(text, checkpoint_file=ckpt)
    assert calls == ['AAA', 'BBB']
    assert os.path.exists(ckpt)
    with open(ckpt, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    assert saved['last_chunk'] == 1

    # Run 2: resume — only the remaining chunks get translated
    _install(monkeypatch, calls, crash_after=None)
    out = cp.translate_chunks(text, checkpoint_file=ckpt)

    assert calls == ['AAA', 'BBB', 'CCC', 'DDD']
    assert out == 'TR:AAA\n\nTR:BBB\n\nTR:CCC\n\nTR:DDD'
    assert not os.path.exists(ckpt)  # removed after success


def test_no_checkpoint_behavior_unchanged(tmp_path, monkeypatch):
    calls = []
    _install(monkeypatch, calls)
    out = cp.translate_chunks('AAA\n\nBBB')
    assert calls == ['AAA', 'BBB']
    assert out == 'TR:AAA\n\nTR:BBB'
