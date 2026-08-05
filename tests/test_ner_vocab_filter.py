"""A3: make_vocab must not silently drop entities due to tuple IndexError."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class _FakeEnt:
    def __init__(self, text, label):
        self.text = text
        self.label_ = label
        self.vector_norm = 1.0


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


def test_make_vocab_returns_entities():
    import src.ner as ner_module

    def _fake_nlp(text, disable=None):
        return _FakeDoc([_FakeEnt("Alice", "PERSON") for _ in range(6)])

    def _fake_get_nlp(model_name, max_length=200000):
        return _fake_nlp

    orig = ner_module._get_nlp
    ner_module._get_nlp = _fake_get_nlp
    try:
        text = "Alice met the queen near the river. " * 6
        result = ner_module.make_vocab(text, min_count_ner=5, min_count_word=1000)
    finally:
        ner_module._get_nlp = orig

    assert result
    assert "Alice" in result
