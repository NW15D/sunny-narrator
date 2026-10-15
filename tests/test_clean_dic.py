"""scripts/clean_dic.py: the cleaned .dic loads back without losing fields."""
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location('clean_dic', ROOT / 'scripts' / 'clean_dic.py')
clean_dic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clean_dic)

SOURCE = '''# test
Jain tech = джайн-техника, TERM, ,
jain tech = джайн-тех, , ,
Jain-tech = джайн-технология, TERM, ,
Anna = Анна, person, ж, heroine
Ivan = Иван, PERSON, sie,
Foo = "Bar, Baz", NORP, , first, second
Quote = "Он сказал ""да"", и ушёл", TERM, ,
starship = звездолёт, , ,
runcible = ранкибл, , ,
Jain = Джайн, PERSON, they,
Jains = Джайн, PERSON, ,
no separator line
'''


def _run(tmp_path, monkeypatch, *args):
    src = tmp_path / 'book.dic'
    src.write_text(SOURCE, encoding='utf-8')
    monkeypatch.setattr(clean_dic.ner, 'known_words',
                        lambda words: {w for w in words if w in ('starship', 'runcible')})
    monkeypatch.setattr(sys, 'argv', ['clean_dic.py', str(src), *args])
    clean_dic.main()
    return tmp_path / 'book.clean.dic', tmp_path / 'book.clean.report.txt'


def _load(path):
    from src.vocabulary_manager import VocabularyManager
    vm = VocabularyManager.__new__(VocabularyManager)
    vm.dict_file = str(path)
    return {e.source: e for e in vm._load_from_file().values()}


def test_cleaned_dictionary_round_trips(tmp_path, monkeypatch):
    out, report = _run(tmp_path, monkeypatch)
    vocab = _load(out)

    # duplicates by lexicon.word_key: the entry with a category wins; a hyphen is another entry
    assert vocab['Jain tech'].target == 'джайн-техника' and 'jain tech' not in vocab
    assert vocab['Jain-tech'].target == 'джайн-технология'
    # gender synonyms are normalized, an unknown one is kept and reported
    assert (vocab['Anna'].category, vocab['Anna'].gender, vocab['Anna'].notes) == ('PERSON', 'she', 'heroine')
    assert vocab['Ivan'].gender == ''  # kept in the file, ignored (and logged) by the loader
    # commas and quotes survive in every field, the category is not lost
    assert (vocab['Foo'].target, vocab['Foo'].category, vocab['Foo'].notes) == ('Bar, Baz', 'NORP', 'first, second')
    assert vocab['Quote'].target == 'Он сказал "да", и ушёл'
    # an ordinary word is dropped, unless kept; a cut variant is dropped
    assert 'starship' not in vocab and 'runcible' not in vocab
    assert 'Jain' in vocab and 'Jains' not in vocab

    text = report.read_text(encoding='utf-8')
    for section in ('merged, different targets', 'unknown gender (kept)', 'ordinary word',
                    'cut variant', 'skipped'):
        assert f'## {section}' in text
    assert 'Ivan: sie' in text


def test_keep_and_lowercase_term_category(tmp_path, monkeypatch):
    out, _ = _run(tmp_path, monkeypatch, '--keep', 'runcible')
    vocab = _load(out)
    assert vocab['runcible'].category == 'TERM'
    assert 'starship' not in vocab


def test_source_file_is_not_overwritten(tmp_path, monkeypatch):
    import pytest
    src = tmp_path / 'book.dic'
    src.write_text(SOURCE, encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['clean_dic.py', str(src), '-o', str(src)])
    with pytest.raises(SystemExit):
        clean_dic.main()
    assert src.read_text(encoding='utf-8') == SOURCE
