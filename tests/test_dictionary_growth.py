"""
The dictionary grows while a book is translated, in every format.

Characters reported by the synopsis stage (translate_chunk's candidate_sink)
are put into the in-memory index AND, with DICT_AUTO_SAVE, written to the
.dic file (tests/test_dictionary_coverage.py covers the default, memory only), so the very
next chunk already gets them in its prompt. Both pipelines go through
VocabularyManager.record_dictionary_candidates for this.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
import src.vocabulary_manager as vm


def _setup(tmp_path, monkeypatch, book_name):
    book = tmp_path / book_name
    book.write_bytes(b"fake")
    dic = tmp_path / (os.path.splitext(book_name)[0] + ".dic")
    dic.write_text("dragon = дракон, TERM, , \n", encoding='utf-8')
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    monkeypatch.setattr(vm.config, 'dictionary', None)
    monkeypatch.setattr(vm.config, 'ner_opt', False)  # lexical matching, no spaCy model
    monkeypatch.setattr(vm.config, 'source_lang', 'english')
    monkeypatch.setattr(vm.config, 'dict_auto_save', True)
    return book, dic


def test_calibre_translation_adds_new_character_to_file_and_index(tmp_path, monkeypatch):
    book, dic = _setup(tmp_path, monkeypatch, "book.epub")
    prompts = []

    def fake_translate_chunk(**kw):
        prompts.append(sorted(e.source for e in kw['vocab_entries']))
        if len(prompts) == 1:  # synopsis of chunk 1 reports a new character
            kw['candidate_sink'].append({'source': 'Bob', 'target': 'Боб', 'gender': 'he'})
        return "перевод", "synopsis"

    monkeypatch.setattr(cp, '_split_into_chunks_md',
                        lambda text, size: ["Bob saw a dragon.", "Then Bob left."])
    monkeypatch.setattr(cp, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    with patch.object(cp, 'translate_chunk', side_effect=fake_translate_chunk):
        cp.translate_chunks("ignored", book_path=str(book))

    assert prompts == [["dragon"], ["Bob"]], "chunk 2 must already see the new character"
    assert "Bob = Боб, PERSON, he" in dic.read_text(encoding='utf-8')


def test_manager_record_updates_index_and_drops_stale_matches(tmp_path, monkeypatch):
    """Classic pipeline path: TranslationEngine calls the same method."""
    book, dic = _setup(tmp_path, monkeypatch, "book.fb2")
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    assert [e.source for e in manager.get_vocab_for_chunk("Bob and a dragon", 0, 0)] == ["dragon"]

    manager.record_dictionary_candidates([{'source': 'Bob', 'target': 'Боб', 'gender': 'he'}])

    assert manager.vocab['bob'].gender == 'he'
    assert sorted(e.source for e in manager.get_vocab_for_chunk("Bob and a dragon", 0, 0)) == ["Bob", "dragon"]
    assert "Bob = Боб, PERSON, he" in dic.read_text(encoding='utf-8')


def test_ordinary_words_known_to_spacy_are_not_added_as_terms(tmp_path, monkeypatch):
    book, dic = _setup(tmp_path, monkeypatch, "book.fb2")
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.ner_module, 'known_words', lambda words: {'starship'} & set(words))
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()

    manager.record_dictionary_candidates([
        {'source': 'starship', 'target': 'звездолёт', 'gender': '', 'category': 'TERM'},
        {'source': 'spidergun', 'target': 'паукопушка', 'gender': '', 'category': 'TERM'},
    ])

    text = dic.read_text(encoding='utf-8')
    assert "spidergun = паукопушка, TERM" in text and "starship" not in text



def test_fast_mode_grows_the_dictionary_like_the_standard_mode(tmp_path, monkeypatch):
    """FAST_TRANS skips stages 2-4, but the synopsis (the source of the
    candidates) still runs on the real translate_chunk path and its
    candidates reach record_dictionary_candidates. Only a new entry is
    appended; a known one may only get its empty gender filled in
    (the file-level rules: tests/test_dictionary_coverage.py)."""
    import src.utils as u

    source = ("Bob walked to the old tower at dawn and looked at the dragon "
              "sleeping on the hill. Alice followed him with a lantern, and "
              "together they waited for the sun to rise over the quiet valley "
              "while the wind moved through the tall grass around them.")
    draft = "Боб пошёл к старой башне на рассвете. " * 7
    stages = []

    def fake_complete(role, system_prompt, user_prompt, max_tokens, stage, **kw):
        stages.append(stage)
        if stage == u.TranslationStage.SYNOPSIS:
            return ("Боб и Алиса ждут рассвета.\n<genders>\nBob | Боб | he\n"
                    "Alice | Алиса | she\n</genders>"), 10
        return draft, 10

    monkeypatch.setattr(u.config, 'json_mode', False)
    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    sink = []
    u.translate_chunk(source_lang='english', target_lang='russian', source_text=source,
                      outline_text='', vocab_dict={}, vocab_entries=[], style='text',
                      fast_mode=True, candidate_sink=sink)
    assert stages == [u.TranslationStage.INITIAL, u.TranslationStage.SYNOPSIS]
    assert {c['source'] for c in sink} == {'Bob', 'Alice'}

    book, dic = _setup(tmp_path, monkeypatch, "book.fb2")
    dic.write_text("dragon = дракон, TERM, , \nAlice = Алиса, PERSON, , \n", encoding='utf-8')
    before = dic.read_text(encoding='utf-8')

    monkeypatch.setattr(vm.config, 'dict_auto_save', False)
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    manager.record_dictionary_candidates(sink)
    assert 'bob' in manager.vocab, "default: joins the in-memory dictionary"
    assert dic.read_text(encoding='utf-8') == before, "default: the file is not touched"

    monkeypatch.setattr(vm.config, 'dict_auto_save', True)
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    manager.record_dictionary_candidates(sink)
    lines = dic.read_text(encoding='utf-8').splitlines()
    assert lines == ["dragon = дракон, TERM, , ",
                     "Alice = Алиса, PERSON, she, ",  # empty gender filled in, no second line
                     "Bob = Боб, PERSON, he, "]
