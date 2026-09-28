"""
Tests for the DICTIONARY env / --dictionary CLI override.

DICTIONARY points both pipelines at an explicit .dic file instead of the
automatic <book_name>.dic next to the source book. The first version of the
feature only redirected the place where the dictionary is *read* during
translation; dictionary *creation* (classic main(), Calibre run_pipeline
Step 2) and the metadata glossary still used the automatic path, so a run
with a not-yet-existing explicit dictionary built <book>.dic and then
translated without any glossary. These tests pin every place that resolves
the .dic path to the override.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
import src.vocabulary_manager as vm


# ---------------------------------------------------------------------------
# VocabularyManager / get_vocabulary_manager
# ---------------------------------------------------------------------------

def test_manager_path_precedence(tmp_path, monkeypatch):
    book = str(tmp_path / "book.fb2")
    monkeypatch.setattr(vm.config, 'dictionary', None)
    assert vm.VocabularyManager(book).dict_file == str(tmp_path / "book.dic")

    monkeypatch.setattr(vm.config, 'dictionary', str(tmp_path / "env.dic"))
    assert vm.VocabularyManager(book).dict_file == str(tmp_path / "env.dic")

    explicit = str(tmp_path / "cli.dic")
    assert vm.VocabularyManager(book, dict_file=explicit).dict_file == explicit


def test_get_manager_rebuilds_when_path_changes(tmp_path, monkeypatch):
    book = str(tmp_path / "book.fb2")
    monkeypatch.setattr(vm.config, 'dictionary', None)
    monkeypatch.setattr(vm, '_vocabulary_manager', None)

    first = vm.get_vocabulary_manager(book, dict_file=str(tmp_path / "x.dic"))
    assert first.dict_file == str(tmp_path / "x.dic")

    # Dropping the override must not keep serving the stale explicit path
    second = vm.get_vocabulary_manager(book)
    assert second.dict_file == str(tmp_path / "book.dic")

    # Same resolved path -> cached instance is reused
    assert vm.get_vocabulary_manager(book) is second


# ---------------------------------------------------------------------------
# Classic pipeline: main() builds the dictionary at the explicit path
# ---------------------------------------------------------------------------

def test_classic_main_creates_dictionary_at_explicit_path(tmp_path, monkeypatch):
    import app

    book = tmp_path / "book.txt"
    book.write_text("Alice met Bob.\n\nAlice smiled.", encoding='utf-8')
    explicit = tmp_path / "dicts" / "shared.dic"
    explicit.parent.mkdir()

    monkeypatch.setattr(app.config, 'myfile', str(book))
    monkeypatch.setattr(app.config, 'dictionary', str(explicit))
    monkeypatch.setattr(app.config, 'ner_opt', True)
    fake_ner = MagicMock()
    fake_ner.make_vocab.return_value = "Alice [PERSON]\nBob [PERSON]"
    monkeypatch.setattr(app, 'ner', fake_ner)
    monkeypatch.setattr(app.ta, 'vocabulary',
                        lambda *a, **kw: "Alice = Алиса\nBob = Боб")

    with pytest.raises(SystemExit) as exc:
        app.main()

    assert exc.value.code == 0  # "review and restart"
    assert explicit.exists(), "dictionary must be created at DICTIONARY path"
    assert not (tmp_path / "book.dic").exists(), "auto path must stay untouched"


# ---------------------------------------------------------------------------
# Calibre pipeline: Step 2, metadata glossary and translate_chunks
# ---------------------------------------------------------------------------

def _install_calibre_mocks(monkeypatch, extracted):
    monkeypatch.setattr(cp, 'convert_to_markdown',
                        lambda input_path: ("# Chapter\n\nAlice text", {"title": "Alice"}))
    extract_mock = MagicMock(return_value=extracted)
    monkeypatch.setattr(cp, 'extract_dictionary_from_md', extract_mock)
    metadata_mock = MagicMock()
    monkeypatch.setattr(cp, '_translate_output_metadata', metadata_mock)
    translate_mock = MagicMock(return_value="# Глава\n\nТекст про Алису")
    monkeypatch.setattr(cp, 'translate_chunks', translate_mock)

    def _build_output(translated_md, output_format, metadata, **kwargs):
        out = os.path.splitext(kwargs['input_path'])[0] + f".{output_format}"
        with open(out, 'w', encoding='utf-8') as f:
            f.write('OUTPUT')
        return out

    monkeypatch.setattr(cp, 'build_output', MagicMock(side_effect=_build_output))
    report = MagicMock(is_valid=True, issues=[])
    report.summary.return_value = "ok"
    monkeypatch.setattr(cp, 'validate_output', lambda *a, **kw: report)
    return extract_mock, metadata_mock, translate_mock


def test_calibre_builds_missing_dictionary_at_explicit_path(tmp_path, monkeypatch):
    book = tmp_path / "book.epub"
    book.write_bytes(b"fake")
    explicit = tmp_path / "shared.dic"
    extracted = {"Alice": {"target": "Алиса", "category": "PERSON", "gender": "f", "notes": ""}}
    extract_mock, metadata_mock, translate_mock = _install_calibre_mocks(monkeypatch, extracted)
    monkeypatch.setattr(cp, 'save_dictionary',
                        lambda d, path: open(path, 'w', encoding='utf-8').write("Alice = Алиса, PERSON, f,\n"))

    cp.run_pipeline(str(book), output_format="epub", target_lang="russian",
                    skip_validation=True, dict_file=str(explicit))

    assert extract_mock.call_count == 1
    assert explicit.exists(), "Step 2 must write the dictionary to dict_file"
    assert not (tmp_path / "book.dic").exists()
    assert translate_mock.call_args.kwargs['dict_file'] == str(explicit)
    metadata_vocab = metadata_mock.call_args.args[4]
    assert [e['source'] for e in metadata_vocab] == ["Alice"]


def test_calibre_skips_build_when_explicit_dictionary_exists(tmp_path, monkeypatch):
    book = tmp_path / "book.epub"
    book.write_bytes(b"fake")
    explicit = tmp_path / "shared.dic"
    explicit.write_text("Alice = Алиса, PERSON, f,\n", encoding='utf-8')
    extract_mock, metadata_mock, _ = _install_calibre_mocks(monkeypatch, {})

    cp.run_pipeline(str(book), output_format="epub", target_lang="russian",
                    skip_validation=True, dict_file=str(explicit))

    extract_mock.assert_not_called()
    assert not (tmp_path / "book.dic").exists()
    metadata_vocab = metadata_mock.call_args.args[4]
    assert [e['source'] for e in metadata_vocab] == ["Alice"]


def test_calibre_uses_config_dictionary_by_default(tmp_path, monkeypatch):
    book = tmp_path / "book.epub"
    book.write_bytes(b"fake")
    explicit = tmp_path / "env.dic"
    explicit.write_text("Alice = Алиса, PERSON, f,\n", encoding='utf-8')
    _, _, translate_mock = _install_calibre_mocks(monkeypatch, {})
    monkeypatch.setattr(cp.config, 'dictionary', str(explicit))

    cp.run_pipeline(str(book), output_format="epub", target_lang="russian",
                    skip_validation=True)

    assert translate_mock.call_args.kwargs['dict_file'] == str(explicit)
