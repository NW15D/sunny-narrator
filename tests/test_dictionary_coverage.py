"""
A dictionary candidate reported by the synopsis stage is added only when
nothing of it is in the dictionary yet (vocabulary_manager.CandidateMatcher):

- another form of an existing entry is that entry ("Jain nodes" = "Jain node",
  "Gabbleducks" = "gabbleduck"); a hyphen, a space or no separator make
  different entries ("Jain-tech" / "Jain tech", "gabble-duck" / "gabbleduck");
- a phrase containing a known term ("Jain node", "jain shriek" with "Jain")
  is covered by it and would only shadow it with a second translation.

Found entries join the in-memory dictionary; the .dic file is written only
with DICT_AUTO_SAVE (off by default). A resume keeps them via the checkpoint.
"""
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
import src.utils as u
import src.vocabulary_manager as vm
from src import lexicon
from src.vocabulary_manager import apply_dictionary_candidates


def _term(source, target):
    return {'source': source, 'target': target, 'gender': '', 'category': 'TERM'}


def _person(source, target, gender):
    return {'source': source, 'target': target, 'gender': gender, 'category': 'PERSON'}


def test_covering_terms_ignore_case_and_inflection_but_not_separators():
    terms = ["Jain", "Jain node", "Jain tech", "spidergun", "Will"]
    assert lexicon.covering_terms("Jain node", terms, "english") == ["Jain node", "Jain"]
    assert lexicon.covering_terms("jain shriek", terms, "english") == ["Jain"]
    assert lexicon.covering_terms("Jain nodes", terms, "english") == ["Jain node", "Jain"]
    # a hyphenated spelling is another entry, but still contains "Jain"
    assert lexicon.covering_terms("Jain-tech", terms, "english") == ["Jain"]
    assert lexicon.covering_terms("Jain tech", ["Jain-tech"], "english") == []
    assert lexicon.covering_terms("spiderguns battery", terms, "english") == ["spidergun"]
    # a stop-word entry would cover half the language
    assert lexicon.covering_terms("Will power", terms, "english") == []
    assert lexicon.covering_terms("gubbleduck", terms, "english") == []


def test_word_key_merges_case_but_not_separators():
    assert lexicon.word_key("JAIN  Tech") == lexicon.word_key("jain tech") == "jain tech"
    assert lexicon.word_key("Jain-tech") != lexicon.word_key("Jain tech")
    assert lexicon.separators("Jain-tech") == ("-",)
    assert lexicon.separators("Jain mother ship") == (" ", " ")
    assert lexicon.separators("gabbleduck") == ()


def test_jain_compounds_are_not_added_to_the_file(tmp_path):
    dic = tmp_path / "s.dic"
    dic.write_text("Jain = Джайны, ORG, they, \nJain tech = джайновская технология, TERM, , \n",
                   encoding="utf-8")
    candidates = [
        _term("Jain node", "узел Джайна"),
        _term("jain shriek", "крик Джайны"),
        _term("Jain-tech", "джайн-технология"),          # its own entry, but contains "Jain"
        _term("Jain technology", "технология Джайнов"),
        _person("Jain soldier", "солдат Джайнов", "he"),
        _term("spidergun", "паукопушка"),
    ]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (0, 1)
    text = dic.read_text(encoding="utf-8")
    assert "spidergun = паукопушка, TERM" in text
    for junk in ("node", "shriek", "Jain-tech", "technology", "soldier"):
        assert junk not in text


def test_inflected_form_is_the_entry_but_hyphenated_spelling_is_new(tmp_path):
    """series.dic had "gabbleduck = уткотрёп" and then got "gabbleducks"."""
    dic = tmp_path / "s.dic"
    dic.write_text("gabbleduck = уткотрёп, PERSON, it, \nJain-tech = джайн-техника, TERM, , \n",
                   encoding="utf-8")
    candidates = [_term("gabbleducks", "габблдуки"), _term("Gabbleducks", "габблдуки"),
                  _term("gabble-duck", "габбл-утка")]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (0, 1)
    text = dic.read_text(encoding="utf-8")
    assert "gabbleducks" not in text.casefold()
    assert "gabble-duck = габбл-утка, TERM" in text


def test_shorter_candidate_of_one_batch_wins(tmp_path):
    dic = tmp_path / "s.dic"
    dic.write_text("# empty\n", encoding="utf-8")
    candidates = [_term("Jain node", "узел Джайна"), _person("Jain", "Джайн", "they")]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (0, 1)
    text = dic.read_text(encoding="utf-8")
    assert "Jain = Джайн, PERSON, they" in text and "node" not in text


def test_person_with_a_known_part_is_not_added_but_its_own_form_gets_gender(tmp_path):
    dic = tmp_path / "s.dic"
    dic.write_text("Jason = Джейсон, PERSON, , \nOrlandine = Орландина, , , \n", encoding="utf-8")
    candidates = [
        _person("Jason Williams", "Джейсон Уильямс", "he"),   # covered by "Jason"
        _person("ORLANDINE", "Орландина", "she"),            # the same entry in caps
    ]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (1, 0)
    text = dic.read_text(encoding="utf-8")
    assert "Williams" not in text
    assert "Orlandine = Орландина, PERSON, she, " in text


def _manager(tmp_path, monkeypatch, dic_text, auto_save=False):
    book = tmp_path / "book.fb2"
    book.write_bytes(b"fake")
    dic = tmp_path / "book.dic"
    dic.write_text(dic_text, encoding="utf-8")
    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    monkeypatch.setattr(vm.config, 'dictionary', None)
    monkeypatch.setattr(vm.config, 'ner_opt', False)
    monkeypatch.setattr(vm.config, 'source_lang', 'english')
    monkeypatch.setattr(vm.config, 'dict_auto_save', auto_save)
    manager = vm.get_vocabulary_manager(str(book))
    manager.load()
    return manager, dic


def test_without_auto_save_entries_stay_in_memory(tmp_path, monkeypatch):
    original = "Jain = Джайны, ORG, they, \n"
    manager, dic = _manager(tmp_path, monkeypatch, original)

    manager.record_dictionary_candidates([_term("Jain node", "узел Джайна"),
                                          _term("spidergun", "паукопушка")])

    assert dic.read_text(encoding="utf-8") == original
    assert sorted(e.source for e in manager.vocab.values()) == ["Jain", "spidergun"]
    assert [c['source'] for c in manager.session_candidates] == ["spidergun"]
    found = manager.get_vocab_for_chunk("The Jain node fired a spidergun.", 0, 0)
    assert sorted(e.source for e in found) == ["Jain", "spidergun"]


def test_with_auto_save_entries_go_to_the_file(tmp_path, monkeypatch):
    manager, dic = _manager(tmp_path, monkeypatch, "Jain = Джайны, ORG, they, \n", auto_save=True)
    manager.record_dictionary_candidates([_term("Jain node", "узел Джайна"),
                                          _term("spidergun", "паукопушка")])
    text = dic.read_text(encoding="utf-8")
    assert "spidergun = паукопушка, TERM" in text and "node" not in text


def test_restored_session_candidates_do_not_touch_the_file(tmp_path, monkeypatch):
    original = "Jain = Джайны, ORG, they, \n"
    manager, dic = _manager(tmp_path, monkeypatch, original)
    manager.restore_session_candidates([_term("spidergun", "паукопушка")])
    assert "spidergun" in manager.vocab
    assert dic.read_text(encoding="utf-8") == original
    # restored entries are checkpointed again by the resumed run
    assert [c['source'] for c in manager.session_candidates] == ["spidergun"]


def test_duplicate_lines_of_one_entry_keep_the_first(tmp_path, monkeypatch, caplog):
    manager, _ = _manager(tmp_path, monkeypatch,
                          "Jain tech = джайновская технология, TERM, , \n"
                          "jain-tech = джайн-техника, TERM, , \n"
                          "JAIN  tech = ещё вариант, TERM, , \n")
    assert [(e.source, e.target) for e in manager.vocab.values()] == [
        ("Jain tech", "джайновская технология"), ("jain-tech", "джайн-техника")]
    assert "duplicates 'Jain tech'" in caplog.text


def test_synopsis_prompt_lists_the_chunk_glossary():
    entries = [vm.VocabEntry(source="Jain", target="Джайны", category="ORG"),
               vm.VocabEntry(source="spidergun", target="паукопушка")]
    block = u.build_synopsis_glossary(entries)
    assert block == "<glossary>\nJain = Джайны\nspidergun = паукопушка\n</glossary>\n\n"
    assert u.build_synopsis_glossary([]) == ""
    for key in ("user", "user_hunyuan"):
        prompt = u.config.get_prompt("synopsis", key, target_lang="russian", source_text="s",
                                     final_translation="t", characters_block="",
                                     glossary_block=block,
                                     dictionary_rules=u.config.get_prompt("synopsis", "dictionary_rules"))
        assert prompt.startswith("<glossary>\nJain = Джайны")
    assert "<glossary>" in u.config.get_prompt("synopsis", "dictionary_rules")


def test_calibre_resume_keeps_terms_found_before_the_crash(tmp_path, monkeypatch):
    """Chunk 1 finds "spidergun", chunk 2 fails: the resumed run still has
    the term in memory (DICT_AUTO_SAVE off) and passes it to chunk 2."""
    _, dic = _manager(tmp_path, monkeypatch, "Jain = Джайны, ORG, they, \n")
    original = dic.read_text(encoding="utf-8")
    book = tmp_path / "book.epub"
    book.write_bytes(b"fake")
    monkeypatch.setattr(vm.config, 'dictionary', str(dic))
    checkpoint = str(tmp_path / "book.checkpoint.json")
    chunks = ["A spidergun.", "Another spidergun."]
    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda text, size: chunks)
    monkeypatch.setattr(cp, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    monkeypatch.setattr(cp.time, 'sleep', lambda s: None)

    def crash_on_chunk_2(**kw):
        if kw['source_text'] == chunks[1]:
            raise RuntimeError("LLM down")
        kw['candidate_sink'].append(_term("spidergun", "паукопушка"))
        return "перевод", "synopsis"

    with patch.object(cp, 'translate_chunk', side_effect=crash_on_chunk_2), \
            pytest.raises(RuntimeError, match="untranslated"):
        cp.translate_chunks("ignored", book_path=str(book), checkpoint_file=checkpoint,
                            remove_on_success=False)
    saved = json.load(open(checkpoint, encoding="utf-8"))
    assert [c['source'] for c in saved['extra']['session_terms']] == ["spidergun"]

    monkeypatch.setattr(vm, '_vocabulary_manager', None)
    prompts = []

    def record_prompt(**kw):
        prompts.append(sorted(e.source for e in kw['vocab_entries']))
        return "перевод", "synopsis"

    with patch.object(cp, 'translate_chunk', side_effect=record_prompt):
        cp.translate_chunks("ignored", book_path=str(book), checkpoint_file=checkpoint)
    assert prompts == [["spidergun"]]
    assert dic.read_text(encoding="utf-8") == original


def test_classic_checkpoint_roundtrip_of_session_terms(tmp_path, monkeypatch):
    from app import TranslationEngine

    manager, _ = _manager(tmp_path, monkeypatch, "Jain = Джайны, ORG, they, \n")
    engine = TranslationEngine(str(tmp_path / 'run1.txt'))
    engine.vocab_manager = manager
    manager.record_dictionary_candidates([_term("spidergun", "паукопушка")])
    ckpt = str(tmp_path / 'book.checkpoint.json')
    engine.save_checkpoint(ckpt)

    engine2 = TranslationEngine(str(tmp_path / 'run2.txt'))
    engine2.restore_from_checkpoint(json.load(open(ckpt, encoding='utf-8')))
    assert [c['source'] for c in engine2.pending_session_terms] == ["spidergun"]


def test_names_are_compared_by_exact_words(tmp_path):
    """Marie and Mary share the stem "mari" but are different people;
    "Jains" is an inflection of "Jain" and is that entry."""
    dic = tmp_path / "s.dic"
    dic.write_text("Mary = Мэри, PERSON, , \n", encoding="utf-8")
    assert apply_dictionary_candidates(
        str(dic), [_person("Marie", "Мари", "she"), _person("MARY", "Мэри", "she")], "english") == (1, 1)
    text = dic.read_text(encoding="utf-8")
    assert "Mary = Мэри, PERSON, she, " in text and "Marie = Мари, PERSON, she, " in text


def test_acronyms_match_only_themselves(tmp_path):
    """ECS (Earth Central Security) is not EC (Earth Central), though the
    stem of "ecs" is "ec"; "AIs" is still "AI"."""
    dic = tmp_path / "s.dic"
    dic.write_text("EC = ЕЦ, ORG, it, \nAI = ИИ, TERM, , \n", encoding="utf-8")
    candidates = [_person("ECS", "ЦСБЗ", "it"), _term("AIs", "ИИ"), _term("ECS", "ЦСБЗ")]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (0, 1)
    text = dic.read_text(encoding="utf-8")
    assert "ECS = ЦСБЗ, PERSON, it" in text and "AIs" not in text


def test_the_jain_lines_of_series_dic_are_not_added(tmp_path):
    """Every Jain line of the user's series.dic, plus forms the model may send."""
    dic = tmp_path / "s.dic"
    original = "Jain = Джайны, ORG, they, \n"
    dic.write_text(original, encoding="utf-8")
    candidates = [
        _person("a Jain", "Джайн", "he"), _person("Jain soldier", "солдат Джайнов", "he"),
        _term("Jain technology", "технология Джайны"), _term("Jain-tech", "джайновская технология"),
        _term("Jain knot", "узел джайна"), _term("Jain tendrils", "щупальца Джайн"),
        _term("Jain mother ship", "материнский корабль Джайны"),
        _term("Rise of the Jain", "Восхождение Джайнов"), _term("Jain nodes", "узлы Джайна"),
        _person("Jains", "Джайны", "they"), _person("Jain's", "Джайна", "he"),
        _person("JAIN", "Джайн", "he"), _term("jain", "джайн"),
    ]
    assert apply_dictionary_candidates(str(dic), candidates, "english") == (0, 0)
    assert dic.read_text(encoding="utf-8") == original


def test_both_spellings_in_the_dictionary_reach_the_chunk(tmp_path, monkeypatch):
    from src.term_substitution import replace_vocab_in_text

    manager, _ = _manager(tmp_path, monkeypatch,
                          "Jain tech = джайновская технология, TERM, , \n"
                          "Jain-tech = джайн-техника, TERM, , \n")
    text = "The Jain-tech works."
    entries = manager.get_vocab_for_chunk(text, 0, 0)
    assert sorted(e.source for e in entries) == ["Jain tech", "Jain-tech"]
    assert replace_vocab_in_text(text, {e.source: e.target for e in entries}) == "The джайн-техника works."
