"""
The GPU (CuPy) and CPU (NumPy) variants of the per-chunk term matcher give
the same result on a real spaCy model with word vectors.

Skipped without en_core_web_lg (python -m spacy download en_core_web_lg) and,
for the GPU case, without CuPy and a CUDA device (extra [gpu]).
The GPU case loads the model after spacy.prefer_gpu(), as the first chunk of
a real run does, so the vectors live on the GPU. VocabularyManager takes
the GPU variant only with CuPy AND a CUDA build of torch.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

spacy = pytest.importorskip("spacy")
if not spacy.util.is_package("en_core_web_lg"):
    pytest.skip("en_core_web_lg is not installed", allow_module_level=True)

from src import ner

TEXT = ("The Jain nodes pulsed. Mad Hatter fired a spiderguns volley at the wolves, "
        "and the starship drifted past the planet.")
VOCAB = {
    'jain': {'en': 'Jain'},                # lexical
    'jain_node': {'en': 'Jain node'},      # inflected multi-word, shadows "Jain"
    'hatter': {'en': 'Hatter'},            # shadowed by "Mad Hatter"
    'mad_hatter': {'en': 'Mad Hatter'},
    'spidergun': {'en': 'spidergun'},      # stem
    'wolf': {'en': 'wolf'},                # lemma
    'spaceship': {'en': 'spaceship'},      # cosine only: "starship"
    'cucumber': {'en': 'cucumber'},        # absent
}


def _gpu_available():
    if not getattr(ner, 'CUPY_AVAILABLE', False):
        return False
    try:
        return ner.cp.cuda.runtime.getDeviceCount() > 0
    except Exception:
        return False


@pytest.fixture
def fresh_model(monkeypatch):
    from thinc.api import get_current_ops, set_current_ops

    ops = get_current_ops()
    monkeypatch.setattr(ner.config, 'nermodel', 'en_core_web_lg')
    monkeypatch.setattr(ner, '_nlp_cache', {})
    monkeypatch.setattr(ner, '_UNUSABLE_MATCH_MODELS', set())
    monkeypatch.setattr(ner, '_PHRASE_VECTOR_CACHE', {})
    yield
    # prefer_gpu() switches spaCy globally; later tests expect NumPy
    set_current_ops(ops)


def _cpu():
    return sorted(ner.find_matching_words_with_cosine_similarity_cpu(TEXT, VOCAB, 'en'))


def test_cpu_variant(fresh_model):
    found = _cpu()
    assert {'Jain node', 'Mad Hatter', 'spidergun', 'wolf'} <= set(found)
    assert 'Hatter' not in found and 'cucumber' not in found


@pytest.mark.skipif(not _gpu_available(), reason="CuPy or a CUDA device is not available")
def test_gpu_variant_matches_cpu(fresh_model, monkeypatch):
    cpu = _cpu()
    monkeypatch.setattr(ner, '_nlp_cache', {})  # reload on the GPU
    monkeypatch.setattr(ner, '_PHRASE_VECTOR_CACHE', {})
    gpu = sorted(ner.find_matching_words_with_cosine_similarity(TEXT, VOCAB, 'en'))
    assert ner.config.nermodel not in ner._UNUSABLE_MATCH_MODELS, "GPU path fell back to lexical"
    assert gpu == cpu


def _manager(tmp_path, monkeypatch):
    import src.vocabulary_manager as vm

    book = tmp_path / "book.fb2"
    book.write_bytes(b"fake")
    (tmp_path / "book.dic").write_text("Jain = Джайны, ORG, they, \n", encoding="utf-8")
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    monkeypatch.setattr(vm.config, 'dictionary', None)
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.config, 'source_lang', 'english')
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    return manager


@pytest.mark.parametrize("cupy, cuda, expected", [
    (True, True, "gpu"), (True, False, "cpu"), (False, True, "cpu")])
def test_chunk_lookup_picks_gpu_only_with_cupy_and_cuda_torch(tmp_path, monkeypatch, cupy, cuda, expected):
    import torch

    manager = _manager(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(ner, 'CUPY_AVAILABLE', cupy)
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: cuda)
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity',
                        lambda *a, **kw: called.append("gpu") or ['Jain'])
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity_cpu',
                        lambda *a, **kw: called.append("cpu") or ['Jain'])
    assert [e.source for e in manager.get_vocab_for_chunk("The Jain came.", 0, 0)] == ['Jain']
    assert called == [expected]


def _cuda_torch():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


@pytest.mark.skipif(not (_gpu_available() and _cuda_torch()),
                    reason="needs CuPy and a CUDA build of torch")
def test_real_run_uses_the_gpu_matcher(tmp_path, monkeypatch, fresh_model):
    manager = _manager(tmp_path, monkeypatch)
    real_gpu = ner.find_matching_words_with_cosine_similarity
    calls = []
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity',
                        lambda *a, **kw: calls.append(1) or real_gpu(*a, **kw))
    found = manager.get_vocab_for_chunk("The Jain nodes pulsed.", 0, 0)
    assert calls == [1]
    assert [e.source for e in found] == ['Jain']
