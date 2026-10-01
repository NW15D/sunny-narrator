"""
Dictionary building and matching: fixes from the review of the unified
dictionary pipeline.

- A failed build leaves no .dic behind (a partial file used to be loaded by
  the next run as a reviewed dictionary).
- Terms are translated by the proofread LLM, for the languages of the book.
- An explicit --build-dict runs NER even with NER=false.
- Per-chunk matching does not load spaCy when the lexical stage finds every term.
- The series dictionary keeps proper names capitalized and whole.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.ner as ner_module
import src.vocabulary_manager as vm
from src import lexicon


def _llm_reply(terms_text):
    return json.dumps([{"source": t, "target": f"T_{t}", "category": "PERSON"}
                       for t in terms_text.split('\n') if t.strip()])


@pytest.fixture
def fake_ner(monkeypatch):
    fake = MagicMock()
    fake.create_dictionary_from_text.return_value = [
        ("Alice", "PERSON", ""), ("Bob", "PERSON", ""), ("Carol", "PERSON", "")]
    monkeypatch.setattr(vm, 'ner_module', fake)
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.config, 'max_len_chunk', 5)  # one term per LLM call
    return fake


def test_failed_build_leaves_no_dictionary(tmp_path, monkeypatch, fake_ner):
    calls = []

    def flaky(*args):
        calls.append(args)
        if len(calls) == 2:
            raise ConnectionError("LLM down")
        return _llm_reply(args[2])

    monkeypatch.setattr('src.utils.vocabulary', flaky)
    manager = vm.VocabularyManager(str(tmp_path / "book.fb2"), dict_file=str(tmp_path / "book.dic"))

    with pytest.raises(ConnectionError):
        manager.build_dictionary("text")

    assert not (tmp_path / "book.dic").exists(), "partial dictionary must not be left behind"
    assert os.listdir(tmp_path) == []
    assert manager.vocab == {}


def test_build_uses_proofread_model_and_book_languages(tmp_path, monkeypatch, fake_ner):
    calls = []
    monkeypatch.setattr('src.utils.vocabulary',
                        lambda *a: calls.append(a) or _llm_reply(a[2]))
    manager = vm.VocabularyManager(str(tmp_path / "book.epub"), dict_file=str(tmp_path / "book.dic"),
                                   source_lang="japanese", target_lang="english", country="USA")

    manager.build_dictionary("text")

    assert {(a[0], a[1], a[3], a[4]) for a in calls} == {("japanese", "english", "USA", "proofread")}
    assert fake_ner.create_dictionary_from_text.call_args.kwargs['lang'] == "japanese"
    assert fake_ner.create_dictionary_from_text.call_args.kwargs['min_word_length'] == 2
    content = (tmp_path / "book.dic").read_text(encoding='utf-8')
    assert "Alice = T_Alice,PERSON" in content and "Carol = T_Carol,PERSON" in content


def test_explicit_build_runs_ner_even_when_disabled(tmp_path, monkeypatch, fake_ner):
    monkeypatch.setattr(vm.config, 'ner_opt', False)
    monkeypatch.setattr('src.utils.vocabulary', lambda *a: _llm_reply(a[2]))
    manager = vm.VocabularyManager(str(tmp_path / "book.fb2"), dict_file=str(tmp_path / "book.dic"))

    manager.build_dictionary("text", use_ner=True)

    assert fake_ner.create_dictionary_from_text.called
    assert "Alice = T_Alice" in (tmp_path / "book.dic").read_text(encoding='utf-8')


def test_manager_cache_respects_languages(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    monkeypatch.setattr(vm.config, 'dictionary', None)
    book = str(tmp_path / "book.epub")
    first = vm.get_vocabulary_manager(book, source_lang="english")
    assert vm.get_vocabulary_manager(book, source_lang="english") is first
    other = vm.get_vocabulary_manager(book, source_lang="japanese")
    assert other is not first and other.source_lang == "japanese"


def test_matching_skips_spacy_when_lexical_stage_finds_everything(monkeypatch):
    monkeypatch.setattr(ner_module, '_get_nlp', MagicMock(side_effect=AssertionError("spaCy loaded")))
    vocab = {"spidergun": {"en": "spidergun"}, "alice": {"en": "Alice"}}
    matched = ner_module.find_matching_words_with_cosine_similarity_cpu(
        "Alice fired two spiderguns.", vocab, "en")
    assert sorted(matched) == ["Alice", "spidergun"]


def test_matching_survives_failed_model_download(monkeypatch):
    """spacy.cli.download exits via SystemExit; matching must keep the lexical result."""
    monkeypatch.setattr(ner_module, '_UNUSABLE_MATCH_MODELS', set())
    monkeypatch.setattr(ner_module, '_get_nlp', MagicMock(side_effect=SystemExit(1)))
    vocab = {"alice": {"en": "Alice"}, "wolf": {"en": "wolf"}}
    matched = ner_module.find_matching_words_with_cosine_similarity_cpu("Alice ran.", vocab, "en")
    assert matched == ["Alice"]


def test_stop_word_lookup_uses_casefold():
    german = lexicon.get_stop_words("german")
    assert lexicon.is_stop_word("daß", german)
    assert lexicon.is_stop_word("Dass", german)
    assert lexicon.is_stop_word("THE", lexicon.normalize_words(["the"]))


# ---------------------------------------------------------------------------
# Series dictionary: proper names keep their capitals and all their words
# ---------------------------------------------------------------------------

def _require_sm_model():
    spacy = pytest.importorskip("spacy")
    try:
        spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm is not installed")


def test_preferred_form_keeps_capitals_and_prefers_lemma_form():
    from collections import Counter
    assert ner_module._preferred_form(Counter({"Ивана": 5, "Иван": 2}), "иван") == "Иван"
    assert ner_module._preferred_form(Counter({"Wells": 3}), "well") == "Wells"
    assert ner_module._preferred_form(Counter({"alice": 1, "Alice": 4}), "alice") == "Alice"


def test_series_dictionary_keeps_proper_names(tmp_path, monkeypatch):
    _require_sm_model()
    monkeypatch.setattr(ner_module.config, 'nermodel', 'en_core_web_sm')
    monkeypatch.setattr(ner_module.config, 'source_lang', 'english')
    monkeypatch.setattr(ner_module.config, 'dict_frequent_words', False)
    text = ("John Smith arrived in London yesterday. "
            "Mary Johnson met John Smith in London. ") * 5
    for name in ("one.txt", "two.txt"):
        (tmp_path / name).write_text(text, encoding='utf-8')
    modes = []
    monkeypatch.setattr('src.utils.vocabulary',
                        lambda *a: modes.append(a[4]) or "[]")

    out = ner_module.create_series_vocab(str(tmp_path), str(tmp_path / "series.dic"),
                                         min_count_ner=2)

    sources = [line.split(' = ')[0] for line in open(out, encoding='utf-8')
               if ' = ' in line and not line.startswith('#')]
    assert "John Smith" in sources, sources
    assert "London" in sources, sources
    assert not any(s.islower() for s in sources), f"proper names lost their capitals: {sources}"
    assert set(modes) == {"proofread"}
    assert not (tmp_path / "series.dic.tmp").exists()
