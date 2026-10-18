"""
The GPU (CuPy) and CPU (NumPy) variants of the per-chunk term matcher give
the same result on a real spaCy model with word vectors.

Skipped without en_core_web_lg (python -m spacy download en_core_web_lg) and,
for the GPU case, without CuPy and a CUDA device (extra [gpu]).
The GPU case loads the model after spacy.prefer_gpu(), as the first chunk of
a real run does, so the vectors live on the GPU. VocabularyManager takes
the GPU variant only when CuPy is installed AND sees a CUDA device.
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


@pytest.mark.skipif(not ner.gpu_available(), reason="CuPy or a CUDA device is not available")
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
    (tmp_path / "book_ru.dic").write_text("Jain = Джайны, ORG, they, \n", encoding="utf-8")
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    monkeypatch.setattr(vm.config, 'dictionary', None)
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.config, 'source_lang', 'english')
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    return manager


class _FakeCupy:
    """cp.cuda.runtime.getDeviceCount(): a number, or an error (no driver)."""
    def __init__(self, devices):
        def count():
            if devices is None:
                raise RuntimeError("cudaErrorNoDevice")
            return devices
        self.cuda = type('cuda', (), {'runtime': type('runtime', (), {'getDeviceCount': staticmethod(count)})})


@pytest.mark.parametrize("cupy, devices, expected", [
    (True, 1, "gpu"), (True, 0, "cpu"), (True, None, "cpu"), (False, 1, "cpu")])
def test_chunk_lookup_picks_gpu_only_with_cupy_and_a_device(tmp_path, monkeypatch, cupy, devices, expected):
    manager = _manager(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(ner, 'CUPY_AVAILABLE', cupy)
    monkeypatch.setattr(ner, 'cp', _FakeCupy(devices))
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity',
                        lambda *a, **kw: called.append("gpu") or ['Jain'])
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity_cpu',
                        lambda *a, **kw: called.append("cpu") or ['Jain'])
    assert [e.source for e in manager.get_vocab_for_chunk("The Jain came.", 0, 0)] == ['Jain']
    assert called == [expected]


@pytest.mark.skipif(not ner.gpu_available(),
                    reason="needs CuPy and a CUDA device")
def test_real_run_uses_the_gpu_matcher(tmp_path, monkeypatch, fresh_model):
    manager = _manager(tmp_path, monkeypatch)
    real_gpu = ner.find_matching_words_with_cosine_similarity
    calls = []
    monkeypatch.setattr(ner, 'find_matching_words_with_cosine_similarity',
                        lambda *a, **kw: calls.append(1) or real_gpu(*a, **kw))
    found = manager.get_vocab_for_chunk("The Jain nodes pulsed.", 0, 0)
    assert calls == [1]
    assert [e.source for e in found] == ['Jain']
