"""
Frequent ordinary words are not added to a new dictionary by default.

They flooded the .dic with translations of common vocabulary ("window",
"suddenly", ...) and pinned the LLM to one context-free translation of each.
Only named entities go in unless DICT_FREQUENT_WORDS / --frequent-words /
include_words=True asks for frequent words too.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.ner as ner_module

spacy = pytest.importorskip("spacy")
try:
    spacy.load("en_core_web_sm")
except OSError:
    pytest.skip("en_core_web_sm is not installed", allow_module_level=True)

TEXT = ("Alice Morgan opened the window and looked at the garden. " * 20)


@pytest.fixture
def english_sm(monkeypatch):
    monkeypatch.setattr(ner_module.config, 'nermodel', 'en_core_web_sm')
    monkeypatch.setattr(ner_module.config, 'source_lang', 'english')


def _terms(result):
    return [line.strip() for line in (result or "").splitlines() if line.strip()]


def test_frequent_words_off_by_default(english_sm, monkeypatch):
    monkeypatch.setattr(ner_module.config, 'dict_frequent_words', False)
    terms = _terms(ner_module.make_vocab(TEXT, min_count_ner=5, min_count_word=5))
    assert any(t.startswith("Alice Morgan") for t in terms)
    assert "window" not in terms and "garden" not in terms


def test_frequent_words_on_request(english_sm, monkeypatch):
    monkeypatch.setattr(ner_module.config, 'dict_frequent_words', False)
    terms = _terms(ner_module.make_vocab(TEXT, min_count_ner=5, min_count_word=5, include_words=True))
    assert "window" in terms and "garden" in terms


def test_env_setting_enables_frequent_words(english_sm, monkeypatch):
    monkeypatch.setattr(ner_module.config, 'dict_frequent_words', True)
    terms = _terms(ner_module.make_vocab(TEXT, min_count_ner=5, min_count_word=5))
    assert "window" in terms


def test_config_default_is_off(monkeypatch):
    from src.config import Config
    monkeypatch.delenv('DICT_FREQUENT_WORDS', raising=False)
    assert Config().dict_frequent_words is False
