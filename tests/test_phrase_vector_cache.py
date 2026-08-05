"""F4: phrase vector cache — vocab words must not be re-processed per chunk."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src import ner


class _FakeDoc:
    def __init__(self, vector):
        self._vector = np.asarray(vector, dtype=np.float32)

    @property
    def vector(self):
        return self._vector

    @property
    def vector_norm(self):
        return float(np.linalg.norm(self._vector))


class _FakeNlp:
    """Counts pipe calls; word 'aaa' has a vector, 'zzz' has none."""

    def __init__(self):
        self.pipe_calls = 0

    def pipe(self, texts, disable=None):
        self.pipe_calls += 1
        return [_FakeDoc([1.0, 0.0]) if t == "aaa" else _FakeDoc([0.0, 0.0]) for t in texts]


def test_phrase_vector_cached():
    ner._PHRASE_VECTOR_CACHE.clear()
    nlp = _FakeNlp()
    v1 = ner._get_phrase_vector("aaa", nlp)
    v2 = ner._get_phrase_vector("aaa", nlp)
    assert v1 is not None
    assert np.array_equal(v1, v2)
    assert nlp.pipe_calls == 1  # второй вызов взят из кеша


def test_phrase_vector_none_cached():
    ner._PHRASE_VECTOR_CACHE.clear()
    nlp = _FakeNlp()
    assert ner._get_phrase_vector("zzz", nlp) is None
    assert ner._get_phrase_vector("zzz", nlp) is None
    assert nlp.pipe_calls == 1
