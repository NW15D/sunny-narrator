"""A3: make_vocab must not silently drop entities due to tuple IndexError."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class _FakeEnt:
    def __init__(self, text, label):
        self.text = text
        self.label_ = label
        self.vector_norm = 1.0

    def __getitem__(self, index):
        # like a spaCy Span: its last token carries the morphology
        class _Token:
            tag_ = ""
            lemma_ = ""
        return _Token()


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


def test_labels_of_every_model_family_map_to_dictionary_categories():
    import src.ner as ner
    assert {ner._normalize_label(l) for l in ("PER", "persName", "PS", "PERSON")} == {"PERSON"}
    assert {ner._normalize_label(l) for l in ("GPE", "placeName", "LC", "FAC")} == {"LOC"}
    assert {ner._normalize_label(l) for l in ("NORP", "MISC")} == {"TERM"}


def test_one_entry_per_entity_with_the_majority_category():
    from collections import Counter
    import src.ner as ner
    assert ner._majority_category(Counter({'ORG': 256, 'PERSON': 2})) == 'ORG'
    assert ner._majority_category(Counter({'ORG': 3, 'PERSON': 3})) == 'PERSON'


def test_a_russian_book_gives_its_characters_in_the_nominative():
    import pytest
    from spacy.util import is_package
    if not is_package("ru_core_news_sm"):
        pytest.skip("ru_core_news_sm not installed")
    import src.ner as ner
    old = ner.config.nermodel
    ner.config.nermodel = "ru_core_news_sm"
    try:
        text = "Анна пришла в Москву. Анна сказала, что Иван уехал в Париж. Ивана ждали в Москве. Москва спала. " * 6
        terms = {t: c for t, c, _ in ner.create_dictionary_from_text(text, min_count_ner=2, lang='russian')}
    finally:
        ner.config.nermodel = old
    assert terms.get("Анна") == "PERSON" and terms.get("Иван") == "PERSON"   # WikiNER PER
    assert terms.get("Москва") == "LOC" and "Москву" not in terms
