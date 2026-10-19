"""DEF-C2: two translate_chunks runs share one VocabularyManager.

In a parallel run one worker records the dictionary candidates of its draft
synopsis while the other worker matches the vocabulary for its own chunk
(iterating `self.vocab` / the matched-terms cache). With no locking in
VocabularyManager the resize mid-iteration raises RuntimeError ("dictionary
changed size during iteration"), which stops the whole book — and, when the
crash does not happen, candidates/votes can be lost silently. All reported
candidates must survive the merge, with no exception.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
import src.vocabulary_manager as vm_mod
from src.vocabulary_manager import VocabularyManager, VocabEntry

CHUNKS_PER_BOOK = 60


class _State:
    def __init__(self, text, candidates):
        self.final_translation = text
        self.synopsis = ''
        self.synopsis_candidates = candidates
        self.total_tokens = 0


def _chunk_sources(tag):
    # one unique two-word term per chunk; built so one term can never cover
    # another (no shared stems that snowball could collapse)
    return [f'Zorvak{tag}{i} Kimmel{tag}{i}' for i in range(CHUNKS_PER_BOOK)]


def test_parallel_books_share_vocabulary_manager(tmp_path, monkeypatch):
    shared_vm = VocabularyManager(
        book_path=str(tmp_path / 'book.epub'),
        dict_file=str(tmp_path / 'book_ru.dic'),
        source_lang='english', target_lang='russian')
    # As if the .dic had just been loaded: the matching step of one worker
    # iterates this vocabulary while the other worker records its candidates.
    for i in range(300):
        shared_vm.vocab[f'pre{i}'] = VocabEntry(source=f'Pre{i} Word{i}', target=f'Все{i}')

    monkeypatch.setattr(vm_mod.config, 'ner_opt', False)

    def fake_execute(**kwargs):
        text = kwargs['source_text']
        head = text.split(' ', 2)
        source = f'{head[0]} {head[1]}'
        return _State('TR:' + text,
                      [{'source': source, 'target': 'П' + source,
                        'gender': '', 'category': 'TERM'}])

    monkeypatch.setattr(cp._pipeline, 'execute', fake_execute)
    monkeypatch.setattr(cp, 'validate_translation_length', lambda s, d, l: (True, 0.0, False))
    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda text, size: text.split('\n\n'))
    monkeypatch.setattr(cp.config, 'parallel_stages', 1)  # the two threads ARE the parallelism here

    errors = []

    def run(tag):
        book = '\n\n'.join(f'{s} body of chunk' for s in _chunk_sources(tag))
        try:
            cp.translate_chunks(book, max_chunk_size=6000, source_lang='english',
                                target_lang='russian', vocab_manager=shared_vm)
        except BaseException as e:  # the race stops the whole book
            errors.append(f'{tag}: {type(e).__name__}: {e}')

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)  # widen the race windows
    threads = [threading.Thread(target=run, args=(tag,)) for tag in ('A', 'B')]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
    finally:
        sys.setswitchinterval(old_interval)

    assert not any(t.is_alive() for t in threads), 'translation threads hung'
    assert errors == [], f'a parallel run failed instead of merging safely: {errors}'

    got = {c['source'] for c in shared_vm.session_candidates
           if isinstance(c, dict) and 'source' in c}
    expected = set(_chunk_sources('A')) | set(_chunk_sources('B'))
    assert got == expected, f'candidates lost in the merge: {sorted(expected - got)}'