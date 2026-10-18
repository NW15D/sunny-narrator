"""
app.py dict review / the check before a translation (src/dict_review.py):
categories and genders of a .dic checked against the
source book (NER labels, pronouns), without an LLM. The source .dic is never
changed; only sure findings reach the reviewed file, the rest the report.
"""
import collections
import os
import sys
from pathlib import Path

import pytest
from spacy.util import is_package

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import commands
from src import dict_review as rd

ROOT = Path(__file__).resolve().parent.parent


def _ev(mentions=10, lowercase=0, labels=None, pronouns=None):
    ev = rd.Evidence()
    ev.mentions, ev.lowercase = mentions, lowercase
    ev.labels.update(labels or {})
    ev.pronouns.update(pronouns or {})
    return ev


def _row(source, category='PERSON', gender=''):
    return {'line': 0, 'source': source, 'target': source, 'category': category,
            'gender': gender, 'notes': ''}


def test_sure_findings_change_the_row_the_rest_goes_to_the_report():
    rows = [_row("Vashti"), _row("Vorta", gender='she'), _row("dracomen"), _row("Kuno"),
            _row("Shelley", gender='she'), _row("Siren", category='TERM'), _row("Ghost"),
            _row("Wessex")]
    evidence = {
        0: _ev(pronouns={'she': 41, 'he': 3}),
        1: _ev(labels={'ORG': 12, 'PERSON': 1}),
        2: _ev(lowercase=9),
        3: _ev(pronouns={'he': 17, 'she': 14}),            # a two-person scene: not sure
        4: _ev(pronouns={'he': 5}),
        5: _ev(labels={'PERSON': 11, 'ORG': 1}, pronouns={'he': 7}),
        7: _ev(labels={'LOC': 9}),
    }
    report = collections.defaultdict(list)
    changed = rd.review(rows, evidence, min_votes=5, ratio=0.85, report=report)

    assert [(r['source'], r['category'], r['gender']) for r in rows] == [
        ("Vashti", "PERSON", "she"),
        ("Vorta", "PERSON", "she"),    # a gender set by hand keeps it a person, whatever NER says
        ("dracomen", "TERM", ""),      # written lowercase in the book
        ("Kuno", "PERSON", ""),
        ("Shelley", "PERSON", "she"),  # the .dic is the user's: only reported
        ("Siren", "PERSON", ""),       # a new person gets no gender in the same run
        ("Ghost", "PERSON", ""),
        ("Wessex", "LOC", ""),         # NER says a place, nobody calls it he/she
    ]
    assert changed == 4
    assert report['gender conflict (not changed)'] == [
        "Shelley = Shelley: the .dic says she, the book he (he ×5)"]
    assert any("the .dic has a gender (she)" in line for line in report['category: not sure (not changed)'])
    assert report['not found in the book'] == ["Ghost = Ghost"]
    assert any(line.startswith("Kuno = Kuno") for line in report['gender not sure (not set)'])


def test_weak_evidence_changes_nothing():
    rows = [_row("Dolores"), _row("Napoleon")]
    report = collections.defaultdict(list)
    evidence = {0: _ev(labels={'ORG': 5, 'PERSON': 2}), 1: _ev(pronouns={'he': 4})}
    assert rd.review(rows, evidence, min_votes=5, ratio=0.85, report=report) == 0
    assert rows[0]['category'] == 'PERSON' and rows[1]['gender'] == ''
    assert report['category: not sure (not changed)'] and report['gender not sure (not set)']


def test_rows_keep_their_lines_and_gender_spellings_are_normalized(tmp_path):
    dic = tmp_path / "b.dic"
    dic.write_text("# comment\nVashti = Вашти, PERSON, female, \nFoo = \"Bar, Baz\", TERM, , note\n",
                   encoding="utf-8")
    lines, rows = rd.read_rows(dic)
    assert [(r['line'], r['source'], r['target'], r['gender']) for r in rows] == [
        (1, "Vashti", "Вашти", "she"), (2, "Foo", "Bar, Baz", "")]
    assert lines[0] == "# comment"


@pytest.mark.skipif(not is_package("en_core_web_lg"), reason="en_core_web_lg not installed")
def test_the_demo_book(tmp_path, monkeypatch):
    out = tmp_path / "em.reviewed.dic"
    assert commands.run(['dict', 'review', str(ROOT / "books/eternal-moment.pg.epub"),
                "--dic", str(ROOT / "tests/data/eternal-moment.pg_fr.dic"), "--model", "en_core_web_lg",
                "-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Vashti = Vashti,PERSON,she," in text and "Andrews = Andrews,PERSON,he," in text
    # a village, but the user's dictionary says PERSON and people around it are
    # he/she: the dictionary wins, the report asks
    report = (out.with_name("em.reviewed.report.txt")).read_text(encoding="utf-8")
    assert "Vorta = Vorta, PERSON: NER ORG" in report
    assert "Kuno = Kuno,PERSON,," in text               # the evidence is mixed: left empty
    report = out.with_name("em.reviewed.report.txt").read_text(encoding="utf-8")
    assert "## gender set" in report and "## gender not sure (not set)" in report


def test_particles_hyphens_and_apostrophes_are_names(tmp_path):
    """"de la Vega" is not a lowercase word; "Mary-Ann" and "O'Brien" are
    found by the tokenizer of the book's text."""
    import spacy
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    rows = [_row("de la Vega", gender="he"), _row("Mary-Ann"), _row("O'Brien")]
    text = ["Then de la Vega came. Later de la Vega left, and Mary-Ann saw O'Brien."] * 6
    evidence = rd.collect(text, rows, nlp)
    assert evidence[0].mentions == 12 and evidence[0].lowercase == 0
    assert evidence[1].mentions == 6 and evidence[2].mentions == 6


def test_only_the_changed_rows_are_rewritten(tmp_path, monkeypatch):
    dic = tmp_path / "b.dic"
    dic.write_text("# my notes\nKuno = Куно, Person, male, son\nVashti = Вашти, PERSON, , \n",
                   encoding="utf-8")
    lines, rows = rd.read_rows(dic)
    report = collections.defaultdict(list)
    rd.review(rows, {1: _ev(pronouns={'she': 9})}, min_votes=5, ratio=0.85, report=report)
    assert [r.get('changed', False) for r in rows] == [False, True]


def test_a_person_the_book_calls_he_or_she_keeps_its_category():
    """NER tags invented names ORG (Trike, Cog, the Client): pronouns win."""
    rows = [_row("Trike", gender="he"), _row("Wheel")]
    evidence = {0: _ev(labels={'ORG': 256, 'PERSON': 2}, pronouns={'he': 40}),
                1: _ev(labels={'ORG': 32})}
    report = collections.defaultdict(list)
    rd.review(rows, evidence, min_votes=5, ratio=0.85, report=report)
    assert (rows[0]['category'], rows[0]['gender']) == ("PERSON", "he")
    assert rows[1]['category'] == "ORG"
    assert any("calls it he (40 of 40" in line for line in report["category: not sure (not changed)"])


def test_lowercase_words_are_not_mentions_of_a_capitalized_name():
    import spacy
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    rows = [_row("Stone"), _row("dracomen")]
    text = ["He threw a stone at the stone wall. Stone laughed. The dracomen came."] * 6
    evidence = rd.collect(text, rows, nlp)
    assert (evidence[0].mentions, evidence[0].lowercase) == (6, 0)
    assert (evidence[1].mentions, evidence[1].lowercase) == (6, 6)
    report = collections.defaultdict(list)
    rd.review(rows, evidence, min_votes=5, ratio=0.85, report=report)
    assert [r['category'] for r in rows] == ["PERSON", "TERM"]


# --- the check before a translation (preflight) -------------------------------

def _manager(tmp_path, monkeypatch, dic_text, model, lang="english"):
    import src.vocabulary_manager as vm
    book = tmp_path / "book.txt"
    book.write_text("x", encoding="utf-8")
    dic = tmp_path / "book.dic"
    dic.write_text(dic_text, encoding="utf-8")
    monkeypatch.setattr(vm.config, 'dict_check', True)
    monkeypatch.setattr(vm.config, 'nermodel', model)
    monkeypatch.setattr(vm.config, 'dict_autofix', True)
    monkeypatch.setattr(vm.config, 'dict_force', False)
    manager = vm.VocabularyManager(str(book), dict_file=str(dic), source_lang=lang)
    return manager, dic


EN_TEXT = "\n\n".join(["Vashti said that she was tired and she slept."] * 6)


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_preflight_fixes_the_run_not_the_file(tmp_path, monkeypatch, caplog):
    manager, dic = _manager(tmp_path, monkeypatch, "Vashti = Вашти, PERSON, he, \n", "en_core_web_sm")
    before = dic.read_text(encoding="utf-8")
    manager.initialize(source_text=EN_TEXT)
    assert manager.vocab['vashti'].gender == 'she'                   # the book says she, for this run
    assert dic.read_text(encoding="utf-8") == before                  # the .dic is the user's
    assert "Vashti = Вашти,PERSON,she," in (tmp_path / "book.reviewed.dic").read_text(encoding="utf-8")
    assert "gender changed (the book disagrees)" in (tmp_path / "book.dictcheck.txt").read_text(encoding="utf-8")
    assert (tmp_path / "book.dictcheck.json").exists()

    caplog.clear()
    caplog.set_level("INFO")
    manager.initialize(source_text=EN_TEXT)                           # cached: the book is not parsed again
    assert "cached" in caplog.text and manager.vocab['vashti'].gender == 'she'


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_without_autofix_a_contradiction_stops_the_run_unless_forced(tmp_path, monkeypatch):
    import src.vocabulary_manager as vm
    manager, _ = _manager(tmp_path, monkeypatch, "Vashti = Вашти, PERSON, he, \n", "en_core_web_sm")
    monkeypatch.setattr(vm.config, 'dict_autofix', False)
    with pytest.raises(rd.DictionaryCheckFailed):
        manager.initialize(source_text=EN_TEXT)
    monkeypatch.setattr(vm.config, 'dict_force', True)
    manager.initialize(source_text=EN_TEXT)
    assert manager.vocab['vashti'].gender == 'he'                     # as is


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_filling_an_empty_category_is_no_contradiction(tmp_path, monkeypatch):
    import src.vocabulary_manager as vm
    manager, _ = _manager(tmp_path, monkeypatch, "Vashti = Вашти, , she, \n", "en_core_web_sm")
    monkeypatch.setattr(vm.config, 'dict_autofix', False)
    manager.initialize(source_text=EN_TEXT)                           # does not stop
    assert "— -> PERSON" in (tmp_path / "book.dictcheck.txt").read_text(encoding="utf-8")
    assert manager.vocab['vashti'].category == ''                     # not applied: no autofix


def test_dict_convert_returns_its_code(monkeypatch, tmp_path):
    from src import commands, dict_convert
    monkeypatch.setattr(dict_convert, 'make_client', lambda: None)
    monkeypatch.setattr(dict_convert, 'convert', lambda dic, code, *a: code == 'fr')
    dic = tmp_path / "book.dic"
    assert commands.run(['dict', 'convert', str(dic), 'fr']) == 0
    assert commands.run(['dict', 'convert', str(dic), 'fr', 'es']) == 1


def test_dict_force_is_on_by_default(monkeypatch):
    from src.config import Config
    monkeypatch.delenv('DICT_FORCE', raising=False)
    assert Config().dict_force is True                                # --no-autofix alone goes on
    monkeypatch.setenv('DICT_FORCE', 'false')
    assert Config().dict_force is False                               # stops on a contradiction


@pytest.mark.skipif(not is_package("ru_core_news_sm"), reason="ru_core_news_sm not installed")
def test_a_russian_source_book(tmp_path, monkeypatch):
    """ru morphology writes Person=Third, NER labels PER: both are understood."""
    manager, _ = _manager(tmp_path, monkeypatch, "Анна = Anna, PERSON, , \n", "ru_core_news_sm", "russian")
    manager.initialize(source_text="\n\n".join(["Анна сказала, что она устала, и она уснула."] * 6))
    assert manager.vocab['анна'].gender == 'she'


@pytest.mark.skipif(not is_package("zh_core_web_sm"), reason="zh_core_web_sm not installed")
def test_chinese_pronouns_have_no_gender_feature_but_a_gender():
    import spacy
    nlp = spacy.load("zh_core_web_sm")
    genders = [rd._pronoun_gender(t, rd.PRONOUN_GENDER["zh"]) for t in nlp("她说他很累。")]
    assert "she" in genders and "he" in genders


@pytest.mark.skipif(not is_package("xx_ent_wiki_sm"), reason="xx_ent_wiki_sm not installed")
def test_a_model_without_a_parser_gets_sentences():
    nlp = rd._load_model("xx_ent_wiki_sm")
    assert list(nlp("Anna came. Kuno left.").sents)[1].text == "Kuno left."


# --- building a dictionary: categories and genders from the book --------------

def test_a_form_of_address_decides_and_contradicting_pronouns_leave_it_unsure():
    rows = [_row("Miss Raby"), _row("Michael"), _row("Harbottle")]
    evidence = {0: _ev(pronouns={'he': 9}),                                # the entry says Miss
                1: _ev(pronouns={'he': 3}), 2: _ev(pronouns={'he': 6, 'she': 1})}
    evidence[1].honorifics.update({'he': 6})                              # "Mr. Michael" ×6
    evidence[2].honorifics.update({'she': 1})                             # "Miss Harbottle" once
    report = collections.defaultdict(list)
    rd.review(rows, evidence, min_votes=4, ratio=0.85, report=report)
    assert [r['gender'] for r in rows] == ['she', 'he', '']
    assert rd.honorific_gender("Signora Cantù") == 'she' and rd.honorific_gender("Мисс Хэддон") == 'she'
    assert rd.honorific_gender("Miss") is None


def test_a_built_dictionary_trusts_pronouns_over_ner_labels():
    rows = [_row("Trike", category="ORG"), _row("dell", category="ORG"), _row("Vorta", category="ORG")]
    evidence = {0: _ev(labels={'ORG': 256}, pronouns={'he': 40}),
                1: _ev(labels={'ORG': 5}, lowercase=5),
                2: _ev(labels={'ORG': 12}, pronouns={'she': 3, 'he': 3})}
    report = collections.defaultdict(list)
    rd.review(rows, evidence, 4, 0.85, report, fix_conflicts=True, promote_persons=True)
    assert [(r['category'], r['gender']) for r in rows] == [("PERSON", "he"), ("TERM", ""), ("ORG", "")]
    # a reviewed dictionary is the user's: no promotion there
    rows = [_row("Trike", category="ORG")]
    rd.review(rows, {0: _ev(pronouns={'he': 40})}, 4, 0.85, collections.defaultdict(list), fix_conflicts=True)
    assert rows[0]['category'] == "ORG"


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_build_takes_categories_and_genders_from_the_book_not_the_llm(tmp_path, monkeypatch):
    import json
    import re
    import src.utils as u
    import src.vocabulary_manager as vm
    import src.ner as ner
    book = tmp_path / "book.txt"
    text = "\n\n".join(["John walked to the ship. John said that he was tired and he slept."] * 8
                       + ["Miss Raby looked at the sea. Miss Raby smiled."] * 6)
    book.write_text(text, encoding="utf-8")
    sent = []

    def fake_vocabulary(source_lang, target_lang, terms, country, role):
        sent.append(terms)
        names = [re.sub(r'\s*\[[^\]]*\]$', '', line) for line in terms.splitlines() if line.strip()]
        # the LLM guesses categories and genders - they must not reach the .dic
        return json.dumps({"terms": [{"source": n, "target": n.upper(), "category": "LOC", "gender": "she"}
                                     for n in names]})

    monkeypatch.setattr(u, 'vocabulary', fake_vocabulary)
    monkeypatch.setattr(vm.config, 'dict_check', True)
    monkeypatch.setattr(vm.config, 'nermodel', 'en_core_web_sm')
    monkeypatch.setattr(ner.config, 'nermodel', 'en_core_web_sm')
    manager = vm.VocabularyManager(str(book), dict_file=str(tmp_path / "book.dic"), source_lang="english")
    manager.build_dictionary(source_text=text, min_count_ner=3, use_ner=True)

    assert any("[" in terms for terms in sent), "the category goes to the LLM as a hint"
    entries = {e.source: e for e in vm.VocabularyManager(str(book), dict_file=str(tmp_path / "book.dic"))
               .load().values()}
    # the LLM said LOC/she for everything: the .dic has NER's category and the book's gender
    assert (entries["John"].category, entries["John"].gender, entries["John"].target) == ("PERSON", "he", "JOHN")
    assert (entries["Raby"].category, entries["Raby"].gender) == ("PERSON", "she")   # "Miss" before the name


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_a_series_dictionary_gets_a_reviewed_copy_per_book(tmp_path, monkeypatch):
    """One series.dic, two books: each run fixes the dictionary for itself
    only, series.dic stays as it is, and the findings do not overwrite each
    other."""
    import src.vocabulary_manager as vm
    monkeypatch.setattr(vm.config, 'dict_check', True)
    monkeypatch.setattr(vm.config, 'nermodel', 'en_core_web_sm')
    monkeypatch.setattr(vm.config, 'dict_autofix', True)
    dic = tmp_path / "series.dic"
    dic.write_text("Vashti = Вашти, PERSON, he, \n", encoding="utf-8")
    before = dic.read_text(encoding="utf-8")
    for name in ("book1", "book2"):
        book = tmp_path / f"{name}.txt"
        book.write_text("x", encoding="utf-8")
        manager = vm.VocabularyManager(str(book), dict_file=str(dic), source_lang="english")
        manager.initialize(source_text=EN_TEXT)
        assert manager.vocab['vashti'].gender == 'she'
        assert (tmp_path / f"series.{name}.reviewed.dic").exists()
        assert (tmp_path / f"{name}.dictcheck.txt").exists()
    assert dic.read_text(encoding="utf-8") == before


# --- ultrareview of 2026-10-15 -------------------------------------------------

def test_a_dotted_title_is_a_form_of_address():
    """English keeps "Mr." one token: "Mrs. Moore" must count."""
    import spacy
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    rows = [_row("Moore"), _row("Andrews")]
    evidence = rd.collect(["Mrs. Moore smiled at him. Mr. Andrews left."] * 3, rows, nlp)
    assert dict(evidence[0].honorifics) == {'she': 3} and dict(evidence[1].honorifics) == {'he': 3}


def test_a_reviewed_person_keeps_its_category_with_enough_he_or_she():
    """Mixed pronouns are not sure of a gender, but 4+ of them say "a person"
    (Cog); one "He walked on to Vorta." says nothing of the village."""
    rows = [_row("Cog"), _row("Vorta"), _row("Wheel")]
    evidence = {0: _ev(labels={'ORG': 20}, pronouns={'he': 3, 'she': 2}),
                1: _ev(labels={'ORG': 20}, pronouns={'he': 1}),
                2: _ev(labels={'ORG': 20})}
    rd.review(rows, evidence, 4, 0.85, collections.defaultdict(list), fix_conflicts=True)
    assert [r['category'] for r in rows] == ["PERSON", "ORG", "ORG"]


def test_reports_are_not_books_of_a_series(tmp_path):
    import src.ner as ner
    for name in ("book1.epub", "book2.txt", "book1.dictcheck.txt", "series.reviewed.report.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [os.path.basename(f) for f in ner.series_book_files(str(tmp_path))] == ["book1.epub", "book2.txt"]


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_a_read_only_dictionary_does_not_stop_the_run(tmp_path, monkeypatch):
    manager, dic = _manager(tmp_path, monkeypatch, "Vashti = Вашти, PERSON, he, \n", "en_core_web_sm")
    monkeypatch.setattr(rd, "_write_reviewed", lambda *a, **k: (_ for _ in ()).throw(PermissionError("ro")))
    manager.initialize(source_text=EN_TEXT)
    assert manager.vocab['vashti'].gender == 'she'


@pytest.mark.skipif(not is_package("en_core_web_sm"), reason="en_core_web_sm not installed")
def test_an_edited_gender_reuses_the_evidence_of_the_book(tmp_path, monkeypatch, caplog):
    manager, dic = _manager(tmp_path, monkeypatch, "Vashti = Вашти, PERSON, he, \n", "en_core_web_sm")
    manager.initialize(source_text=EN_TEXT)
    dic.write_text("Vashti = Вашти, PERSON, she, \n", encoding="utf-8")   # the user fixes the .dic
    caplog.set_level("INFO")
    manager.initialize(source_text=EN_TEXT)
    assert "evidence of this book is cached" in caplog.text


def test_a_changed_category_parses_the_book_again():
    rows = [_row("Trike", category="ORG")]
    key = rd._entries_key(rows)
    assert rd._entries_key([_row("Trike", category="PERSON")]) != key
    assert rd._entries_key([_row("Trike", category="ORG", gender="he")]) == key   # a gender: reused


def test_convert_keeps_an_entry_without_a_translation_yet(tmp_path):
    from src import dict_convert
    dic = tmp_path / "b.dic"
    dic.write_text("Kuno = , PERSON, he, \nVashti = Вашти, PERSON, she, \n", encoding="utf-8")
    assert [e[0] for e in dict_convert.parse_dic(dic)] == ["Kuno", "Vashti"]
