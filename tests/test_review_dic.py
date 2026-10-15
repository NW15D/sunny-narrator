"""
scripts/review_dic.py: categories and genders of a .dic checked against the
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

from scripts import review_dic as rd

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
            _row("Shelley", gender='she'), _row("Siren", category='TERM'), _row("Ghost")]
    evidence = {
        0: _ev(pronouns={'she': 41, 'he': 3}),
        1: _ev(labels={'ORG': 12, 'PERSON': 1}),
        2: _ev(lowercase=9),
        3: _ev(pronouns={'he': 17, 'she': 14}),            # a two-person scene: not sure
        4: _ev(pronouns={'he': 5}),
        5: _ev(labels={'PERSON': 11, 'ORG': 1}, pronouns={'he': 7}),
    }
    report = collections.defaultdict(list)
    changed = rd.review(rows, evidence, min_votes=5, ratio=0.85, report=report)

    assert [(r['source'], r['category'], r['gender']) for r in rows] == [
        ("Vashti", "PERSON", "she"),
        ("Vorta", "ORG", ""),          # not a person: its gender goes too
        ("dracomen", "TERM", ""),      # written lowercase in the book
        ("Kuno", "PERSON", ""),
        ("Shelley", "PERSON", "she"),  # the .dic is the user's: only reported
        ("Siren", "PERSON", ""),       # a new person gets no gender in the same run
        ("Ghost", "PERSON", ""),
    ]
    assert changed == 4
    assert report['gender conflict (not changed)'] == [
        "Shelley = Shelley: the .dic says she, the book he (he ×5)"]
    assert report['gender cleared (not a person)'] == ["Vorta = Vorta: she"]
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
    monkeypatch.setattr(sys, 'argv', ["review_dic.py", str(ROOT / "books/eternal-moment.pg.epub"),
                "--dic", str(ROOT / "books/eternal-moment.pg.dic"), "--model", "en_core_web_lg",
                "-o", str(out)])
    rd.main()
    text = out.read_text(encoding="utf-8")
    assert "Vashti = Vashti,PERSON,she," in text and "Andrews = Andrews,PERSON,he," in text
    assert "Vorta = Vorta,PERSON" not in text          # a village, not a character
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
