"""PARALLEL_STAGES=2: the translate stages of chunk n+1 overlap with the
proofread stages of chunk n, results stay in book order."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import src.calibre_pipeline as cp
from src.stage_pipeline import StageSequencer, PipelineAborted, chunk_slot, current_slot, DRAFT, COMMITTED


class _State:
    def __init__(self, text, synopsis=''):
        self.final_translation = text
        self.synopsis = synopsis
        self.synopsis_candidates = []
        self.total_tokens = 0


class _Fake:
    """Stand-in for TranslationPipeline.execute that follows its slot protocol."""

    def __init__(self, t_time=0.05, p_time=0.15, fail_on=None):
        self.events = []
        self.outlines = {}
        self.t_time, self.p_time, self.fail_on = t_time, p_time, fail_on
        self.lock = threading.Lock()
        self.p_active = 0
        self.p_overlap = False

    def log(self, *e):
        with self.lock:
            self.events.append((time.monotonic(),) + e)

    def __call__(self, **kw):
        src = kw['source_text']
        self.outlines[src] = kw['outline_text']
        self.log('S1', src)
        time.sleep(self.t_time)
        slot = current_slot()
        synopsis = 'syn(' + src + ')'
        if slot is not None:
            slot.draft_ready(synopsis, 'draft:' + src, [])
            slot.enter_proofread()
        with self.lock:
            self.p_active += 1
            self.p_overlap |= self.p_active > 1
        self.log('P0', src)
        time.sleep(self.p_time)
        if self.fail_on == src:
            with self.lock:
                self.p_active -= 1
            raise KeyboardInterrupt()
        self.log('P1', src)
        with self.lock:
            self.p_active -= 1
        return _State('TR:' + src, synopsis)


def _install(monkeypatch, fake, parallel):
    monkeypatch.setattr(cp._pipeline, 'execute', fake)
    monkeypatch.setattr(cp, 'validate_translation_length', lambda s, d, l: (True, 0.0, False))
    monkeypatch.setattr(cp, '_split_into_chunks_md',
                        lambda text, size: [p for p in text.split('\n\n') if p])
    monkeypatch.setattr(cp.config, 'parallel_stages', 2 if parallel else 1)


TEXT = '\n\n'.join(['AAA', 'BBB', 'CCC', 'DDD', 'EEE'])


def test_same_output_and_faster(monkeypatch):
    seq = _Fake()
    _install(monkeypatch, seq, parallel=False)
    t0 = time.monotonic()
    out_seq = cp.translate_chunks(TEXT)
    t_seq = time.monotonic() - t0

    par = _Fake()
    _install(monkeypatch, par, parallel=True)
    t0 = time.monotonic()
    out_par = cp.translate_chunks(TEXT)
    t_par = time.monotonic() - t0

    assert out_par == out_seq == 'TR:AAA\n\nTR:BBB\n\nTR:CCC\n\nTR:DDD\n\nTR:EEE'
    assert t_par < t_seq * 0.9  # ideal: 0.8 (5 x 0.15 + 0.05 vs 5 x 0.2)
    # one request per GPU: the proofread stages never overlap
    assert not par.p_overlap
    # chunk n+1 gets the (draft) synopsis of chunk n
    assert par.outlines == {'AAA': '', 'BBB': 'syn(AAA)', 'CCC': 'syn(BBB)',
                            'DDD': 'syn(CCC)', 'EEE': 'syn(DDD)'}
    assert seq.outlines == par.outlines
    # S1 of the next chunk starts before the proofread of this one ends
    at = {(e[1], e[2]): e[0] for e in par.events}
    assert at[('S1', 'BBB')] < at[('P1', 'AAA')]


def test_checkpoint_holds_state_of_its_own_chunk(tmp_path, monkeypatch):
    fake = _Fake(fail_on='CCC')
    _install(monkeypatch, fake, parallel=True)
    ckpt = str(tmp_path / 'book.checkpoint.json')
    with pytest.raises(KeyboardInterrupt):
        cp.translate_chunks(TEXT, checkpoint_file=ckpt)
    with open(ckpt, encoding='utf-8') as f:
        saved = json.load(f)
    # BBB's draft was already reported, but the checkpoint of BBB must not know CCC's
    assert saved['last_chunk'] == 1
    assert saved['extra']['outline_text'] == 'syn(BBB)'
    assert saved['extra']['translated_parts'] == ['TR:AAA', 'TR:BBB']

    # resume continues from CCC with BBB's synopsis
    fake2 = _Fake()
    _install(monkeypatch, fake2, parallel=True)
    out = cp.translate_chunks(TEXT, checkpoint_file=ckpt)
    assert out == 'TR:AAA\n\nTR:BBB\n\nTR:CCC\n\nTR:DDD\n\nTR:EEE'
    assert fake2.outlines['CCC'] == 'syn(BBB)'
    assert 'AAA' not in fake2.outlines


def test_failure_does_not_deadlock(monkeypatch):
    fake = _Fake(fail_on='BBB')
    _install(monkeypatch, fake, parallel=True)
    t0 = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        cp.translate_chunks(TEXT)
    assert time.monotonic() - t0 < 10


def test_sequencer_abort_and_resume_offset():
    seq = StageSequencer(first_index=3)
    seq.wait(COMMITTED, 2)  # finished in an earlier run: no wait
    result = []

    def waiter():
        try:
            seq.wait(DRAFT, 3)
        except PipelineAborted:
            result.append('aborted')

    t = threading.Thread(target=waiter)
    t.start()
    seq.abort()
    t.join(5)
    assert result == ['aborted']


def test_slot_marks_draft_even_when_chunk_fails():
    seq = StageSequencer()
    with pytest.raises(ValueError):
        with chunk_slot(seq, 0):
            raise ValueError('boom')
    seq.wait(DRAFT, 0)  # does not block
    assert current_slot() is None


# --- classic (FB2) pipeline ------------------------------------------------

def _classic_chunks(n=6):
    return [{'chunk': f'<p>chunk {i}</p>', 'section_idx': i // 3, 'chunk_idx': i % 3, 'global_id': i}
            for i in range(n)]


def _run_classic(tmp_path, monkeypatch, parallel, name):
    from app import TranslationEngine
    contexts = {}

    def fake(self, chunk, s_idx, c_idx, g_id, context):
        contexts[g_id] = context
        time.sleep(0.02)
        slot = current_slot()
        synopsis = f'syn{g_id} ' * 40       # long enough not to be dropped
        if slot is not None:
            slot.draft_ready(synopsis, chunk, [])
            slot.enter_proofread()
        time.sleep(0.05)
        return chunk.replace('chunk', 'done'), synopsis

    monkeypatch.setattr(TranslationEngine, 'process_chunk_recursive', fake)
    monkeypatch.setattr(app_config(), 'parallel_stages', 2 if parallel else 1)
    monkeypatch.setattr(app_config(), 'fast_trans', False)
    tfile, ckpt = str(tmp_path / f'{name}.fb2'), str(tmp_path / f'{name}.json')
    engine = TranslationEngine(tfile)
    content = engine.process_all_chunks(_classic_chunks(), {}, tfile, ckpt)
    with open(ckpt, encoding='utf-8') as f:
        return content, contexts, json.load(f), engine


def app_config():
    import app
    return app.config


def test_classic_pipeline_same_book_and_contexts(tmp_path, monkeypatch):
    seq = _run_classic(tmp_path, monkeypatch, False, 'seq')
    par = _run_classic(tmp_path, monkeypatch, True, 'par')
    assert par[0] == seq[0]
    assert par[1] == seq[1]
    assert par[2]['synopsis_history'] == seq[2]['synopsis_history']
    assert par[2]['last_chunk'] == 5
    assert '<p>done 5</p>' in par[0] or 'done 5' in par[0]


def test_a_failed_commit_does_not_release_the_next_chunk(tmp_path):
    """The next chunk must not commit (or checkpoint) past a chunk that stopped
    the run: the book would lose the failed one silently."""
    import json
    import os
    import pytest
    import src.calibre_pipeline as cp

    chunks = ["Chunk one text, long enough.", "Chunk two text, long enough.", "Chunk three text."]
    checkpoint = str(tmp_path / "book.checkpoint.json")

    def fake_translate(**kw):
        if kw['source_text'] == chunks[0]:
            return None, ""   # chunk 1 cannot be translated
        return "tr " + kw['source_text'], "syn"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cp, '_split_into_chunks_md', lambda text, size: list(chunks))
        mp.setattr(cp, 'translate_chunk', fake_translate)
        mp.setattr(cp.time, 'sleep', lambda s: None)
        mp.setattr(cp.config, 'parallel_stages', 2)
        mp.setattr(cp, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
        with pytest.raises(cp.ChunkTranslationError):
            cp.translate_chunks("ignored", book_path=str(tmp_path / "book.epub"),
                                checkpoint_file=checkpoint, remove_on_success=False)
    if os.path.exists(checkpoint):
        saved = json.load(open(checkpoint, encoding="utf-8"))
        assert saved['extra']['translated_parts'] == []
