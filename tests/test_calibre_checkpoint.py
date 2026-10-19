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
        self.synopsis_candidates = []
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


# --- DEF-C3: fingerprint must cover country / fast_mode (and style) ----------

def test_resume_discards_checkpoint_when_country_changes(tmp_path, monkeypatch):
    """A checkpoint recorded under one COUNTRY must not be spliced onto a run
    under another: the cultural-context prompts differ, and the first half of
    the book would come out under conditions the user did not ask for."""
    calls = []
    _install(monkeypatch, calls, crash_after=2)

    ckpt = str(tmp_path / 'book.checkpoint.json')
    text = 'AAA\n\nBBB\n\nCCC\n\nDDD'

    with pytest.raises(KeyboardInterrupt):
        cp.translate_chunks(text, checkpoint_file=ckpt, country='Turkey')
    assert calls == ['AAA', 'BBB']

    calls.clear()  # what run 2 actually translates
    _install(monkeypatch, calls, crash_after=None)
    cp.translate_chunks(text, checkpoint_file=ckpt, country='Russia')
    assert calls == ['AAA', 'BBB', 'CCC', 'DDD'], (
        'a checkpoint from a different country must be discarded, not resumed; '
        f'run 2 translated only {calls}')


def test_resume_discards_checkpoint_when_fast_mode_changes(tmp_path, monkeypatch):
    """Half the book translated with reflection and half in fast mode is the
    same class of splicing the fingerprint exists to prevent."""
    calls = []
    _install(monkeypatch, calls, crash_after=2)

    ckpt = str(tmp_path / 'book.checkpoint.json')
    text = 'AAA\n\nBBB\n\nCCC\n\nDDD'

    with pytest.raises(KeyboardInterrupt):
        cp.translate_chunks(text, checkpoint_file=ckpt)
    assert calls == ['AAA', 'BBB']

    calls.clear()  # what run 2 actually translates
    _install(monkeypatch, calls, crash_after=None)
    cp.translate_chunks(text, checkpoint_file=ckpt, fast_mode=True)
    assert calls == ['AAA', 'BBB', 'CCC', 'DDD'], (
        'toggling fast_mode must discard the checkpoint, not resume across it; '
        f'run 2 translated only {calls}')


# --- DEF-C5: a checkpoint save failure is a loud flag, not silence -----------

def test_save_failure_marks_checkpoint_broken_and_run_continues(tmp_path, monkeypatch):
    """Owner's decision (hc-001): on a checkpoint save failure the run
    continues, but the failure must surface — stats.checkpoint_broken=True —
    instead of silently losing all resume protection (ENOSPC, permissions)."""
    calls = []
    _install(monkeypatch, calls)

    real_save = cp.CheckpointManager.save

    def flaky_save(self, chunk_id, *args, **kwargs):
        if chunk_id >= 1:  # e.g. the disk filled halfway through the book
            return False
        return real_save(self, chunk_id, *args, **kwargs)

    monkeypatch.setattr(cp.CheckpointManager, 'save', flaky_save)

    ckpt = str(tmp_path / 'book.checkpoint.json')
    stats = cp.TranslationStats()
    out = cp.translate_chunks('AAA\n\nBBB\n\nCCC', checkpoint_file=ckpt, stats_out=stats)

    assert out == 'TR:AAA\n\nTR:BBB\n\nTR:CCC', 'the book must still be built'
    assert calls == ['AAA', 'BBB', 'CCC']
    assert stats.checkpoint_broken is True, (
        'save failures must be visible in the summary instead of swallowed')
