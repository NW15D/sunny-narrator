"""
app.py dict extend (src/dict_extend.py): a series dictionary carried over to a
new book. NER, the LLM and the book evidence are stubbed; the subject is what
becomes an entry, what only reaches the log, and that the base is not touched.
"""
import datetime
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import commands, dict_extend, dict_review, ner
from src import utils as ta

BASE = """# Vocabulary of the series
# Format: source = target, category, gender, notes

# PERSON
Vashti = Вашти, PERSON, she,
Kuno = Куно, PERSON, ,
Shelley = Шелли, PERSON, she,

# TERM
Jain = Джайны, TERM, ,
"""


@pytest.fixture
def world(tmp_path, monkeypatch):
    book = tmp_path / "vol3.txt"
    book.write_text("Bob went to Zork. Bob smiled.\n\nKuno said he was tired.\n", encoding='utf-8')
    dic = tmp_path / "series.dic"
    dic.write_text(BASE, encoding='utf-8')
    config = ner.config
    monkeypatch.setattr(config, 'source_lang', 'english')
    monkeypatch.setattr(config, 'target_lang', 'russian')
    monkeypatch.setattr(config, 'country', 'Russia')
    sent = []

    candidates = [("Bob", "PERSON", ""), ("Zork", "LOC", ""), ("Vashti", "PERSON", ""),
                  ("Jain node", "TERM", ""), ("vashti", "PERSON", ""), ("starship", "TERM", ""),
                  ("Bob", "PERSON", "")]
    ner_text = []

    def create_dictionary_from_text(text, **kw):
        ner_text.append(text)
        return candidates

    monkeypatch.setattr(ner, 'create_dictionary_from_text', create_dictionary_from_text)
    monkeypatch.setattr(ner, '_get_nlp', lambda name, **kw: type('Nlp', (), {'pipe_names': ['parser']})())
    monkeypatch.setattr(ner, 'known_words', lambda words: {w for w in words if w == 'starship'})

    def vocabulary(source_lang, target_lang, text, country, role):
        sent.append(text)
        answer = {"Bob": "Боб", "Zork": "Зорк"}
        return json.dumps({"terms": [{"source": line.split(' [')[0], "target": answer[line.split(' [')[0]]}
                                     for line in text.splitlines()]})

    monkeypatch.setattr(ta, 'vocabulary', vocabulary)

    def collect(paragraphs, rows, nlp):
        evidence = {}
        for k, row in enumerate(rows):
            ev = dict_review.Evidence()
            ev.mentions = 6
            if row['source'] == 'Bob':
                ev.pronouns.update({'he': 9})
                ev.labels.update({'PERSON': 6})
            elif row['source'] == 'Kuno':
                ev.pronouns.update({'he': 8})
            elif row['source'] == 'Shelley':
                ev.pronouns.update({'he': 6})
            evidence[k] = ev
        return evidence

    monkeypatch.setattr(dict_review, 'collect', collect)
    return tmp_path, book, dic, sent


def test_new_book_adds_only_what_the_dictionary_lacks(world):
    tmp, book, dic, sent = world
    result = dict_extend.extend_file(dic, [book])

    out = result['output'].read_text(encoding='utf-8')
    assert result['output'] == tmp / "series.extended" / "series.dic"
    assert dic.read_text(encoding='utf-8') == BASE, "the source dictionary must not change"
    # a base line is copied as it is, apart from the sure gender of a gender-less entry
    assert "Vashti = Вашти, PERSON, she," in out
    assert "Kuno = Куно,PERSON,he," in out
    assert "Shelley = Шелли, PERSON, she," in out, "a contradicted gender is only reported"
    # new: the book decides the gender, the LLM only translates
    assert "Bob = Боб,PERSON,he," in out
    assert "Zork = Зорк,LOC,," in out
    # never entries: the same entry in another case, a phrase with a known term, an ordinary word
    assert "vashti" not in out and "Jain node" not in out and "starship" not in out
    assert sent == ["Bob [PERSON]\nZork [LOC]"]
    assert result['added'] == 2 and result['changed'] == 1


def test_log_lists_what_was_skipped_and_what_is_disputed(world):
    tmp, book, dic, _ = world
    result = dict_extend.extend_file(dic, [book])
    log = result['report'].read_text(encoding='utf-8')
    assert result['report'].name == "series.extend.report.txt"
    assert "## base: gender conflict (not changed) (1)" in log
    assert "Shelley = Шелли: the .dic says she, the book he" in log
    assert "## base: gender set" in log and "Kuno = Куно: he" in log
    assert "## skipped: covered by existing terms" in log and "Jain node: contains Jain" in log
    assert "## skipped: already in the dictionary" in log
    assert "## skipped: ordinary word" in log and "starship" in log
    assert "## added from books" in log and "Bob = Боб, PERSON" in log


def test_extending_the_result_again_adds_nothing(world):
    tmp, book, dic, sent = world
    first = dict_extend.extend_file(dic, [book])
    second = dict_extend.extend_file(first['output'], [book], output_dir=tmp / "again")
    assert second['added'] == 0
    assert second['output'].read_text(encoding='utf-8') == first['output'].read_text(encoding='utf-8')


def test_merge_adds_missing_entries_and_reports_conflicts(world):
    tmp, _, dic, _ = world
    other = tmp / "other.dic"
    other.write_text("Vashti = Вашта, PERSON, she,\nEmpire = Империя, ORG, ,\n"
                     "Jain tech = Джайн-техника, TERM, ,\nJains = Джайны, TERM, ,\n", encoding='utf-8')
    result = dict_extend.extend_file(dic, merges=[other])
    out = result['output'].read_text(encoding='utf-8')
    log = result['report'].read_text(encoding='utf-8')
    assert "Empire = Империя,ORG" in out
    assert "Вашта" not in out, "the dictionary keeps its own translation"
    assert "Vashti: the dictionary has Vashti = Вашти, other.dic has Вашта" in log
    assert "Jain tech" not in out, "covered by Jain"
    assert result['added'] == 1


def test_nothing_to_extend_with_and_no_overwrite(world):
    tmp, book, dic, _ = world
    with pytest.raises(ValueError, match="nothing to extend"):
        dict_extend.extend_file(dic)
    with pytest.raises(ValueError, match="overwrite"):
        dict_extend.extend_file(dic, [book], output_dir=dic.parent)
    assert dic.read_text(encoding='utf-8') == BASE


def test_llm_failure_leaves_no_result(world, monkeypatch):
    tmp, book, dic, _ = world

    def broken(*a, **kw):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(ta, 'vocabulary', broken)
    with pytest.raises(RuntimeError):
        dict_extend.extend_file(dic, [book])
    assert not (tmp / "series.extended").exists()


def test_command_prints_the_result(world, capsys):
    tmp, book, dic, _ = world
    code = commands.run(['dict', 'extend', str(dic), '--book', str(book), '-o', str(tmp / "out")])
    assert code == 0
    assert "2 added" in capsys.readouterr().out
    assert Path(tmp / "out" / "series.dic").exists()
    assert commands.run(['dict', 'extend', str(dic)]) == 2


def test_new_entries_follow_one_dated_comment(world):
    tmp, book, dic, _ = world
    out = dict_extend.extend_file(dic, [book])['output'].read_text(encoding='utf-8')
    head, block = out.split(f"# new words {datetime.date.today().isoformat()} (vol3.txt)\n")
    assert head.startswith(BASE.split("Kuno")[0])
    assert block == "Bob = Боб,PERSON,he,\nZork = Зорк,LOC,,\n", "only the new entries, by category"


def test_merge_does_not_depend_on_the_order_of_lines(world):
    tmp, _, dic, _ = world
    for name, lines in (("a.dic", ["Zed tech = Зед-техника, TERM, ,", "Zed = Зед, TERM, ,"]),
                        ("b.dic", ["Zed = Зед, TERM, ,", "Zed tech = Зед-техника, TERM, ,"])):
        other = tmp / name
        other.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        result = dict_extend.extend_file(dic, merges=[other], output_dir=tmp / name.replace('.', '_'))
        out = result['output'].read_text(encoding='utf-8')
        assert "Zed = Зед" in out and "Zed tech" not in out, name


def test_ner_reads_the_text_without_markup(world, monkeypatch):
    tmp, _, dic, _ = world
    book = tmp / "vol3.fb2"
    book.write_text('<?xml version="1.0" encoding="utf-8"?>\n<FictionBook '
                    'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">'
                    '<description><title-info><book-title>T</book-title></title-info></description>'
                    '<body><section><p>Bob went to <a l:href="https://x.org">Zork</a>.</p>'
                    '<p>He smiled.</p></section></body></FictionBook>', encoding='utf-8')
    seen = []
    monkeypatch.setattr(ner, 'create_dictionary_from_text', lambda text, **kw: seen.append(text) or [])
    dict_extend.extend_file(dic, [book])
    assert len(seen) == 1 and "Bob went to Zork" in seen[0] and "He smiled." in seen[0]
    assert not any(mark in seen[0] for mark in ('<', 'href', '://'))


def test_an_input_is_never_overwritten(world):
    tmp, book, dic, _ = world
    other_dir = tmp / "other"
    other_dir.mkdir()
    other = other_dir / "series.dic"
    other.write_text("Empire = Империя, ORG, ,\n", encoding='utf-8')
    with pytest.raises(ValueError, match="overwrite"):
        dict_extend.extend_file(dic, merges=[other], output_dir=other_dir)
    assert other.read_text(encoding='utf-8') == "Empire = Империя, ORG, ,\n"


def test_command_reports_a_missing_books_dir(world, capsys):
    tmp, _, dic, _ = world
    assert commands.run(['dict', 'extend', str(dic), '--books-dir', str(tmp / "nope")]) == 2
    assert "error:" in capsys.readouterr().err


def test_model_option_does_not_outlive_the_command(world):
    tmp, book, dic, _ = world
    before = ner.config.nermodel
    dict_extend.extend_file(dic, [book], model="xx_other_model")
    assert ner.config.nermodel == before
