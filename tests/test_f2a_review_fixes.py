"""F2 поток A (review 2026-10-19): major fixes in utils / llm_logger /
vocabulary_manager / dict_clean / dict_convert / epub_repair.

- DEF-M1: one tiktoken cache entry per encoding name, guarded by a lock
  (parallel workers used to swap a single global and reload encodings).
- DEF-M2: a BadRequest that does not name our optional fields fails fast
  (see test_review_fixes_oct19.py, next to the rejected-fields tests).
- DEF-M5: llm_logger builds the whole JSON line and writes it under a lock.
- DEF-M7: atomic writes use unique temp files next to the target and clean
  them on failure (dict_clean.write_atomic, VocabularyManager.build_dictionary).
- DEF-M8: _load_from_file counts unparsable lines and reports them at the end.
- DEF-M10: dict_convert parses with json.loads first, slice fallback second;
  an unparseable answer is warned about instead of raised as a network error.
- DEF-M20: a corrupt OPF manifest gives an error, not a silent [].
"""
import json
import os
import sys
import threading
import time
import zipfile
from datetime import datetime

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import dict_clean, dict_convert, utils
from src import vocabulary_manager as vm
from src.epub_repair import _get_xhtml_files_from_opf, validate_epub
from src.llm_logger import LLMLogger


# ---------------------------------------------------------------------------
# DEF-M1: tiktoken encoding cache (dict + lock)
# ---------------------------------------------------------------------------

class _FakeEncoding:
    def __init__(self, name):
        self.name = name

    def encode(self, text):
        return list(text)


def _reset_tiktoken_cache(monkeypatch):
    monkeypatch.setattr(utils, '_tiktoken_encodings', {}, raising=False)
    monkeypatch.setattr(utils, '_tiktoken_encoding', None, raising=False)


def test_tiktoken_cache_keeps_one_encoding_per_name(monkeypatch):
    loads = []
    _reset_tiktoken_cache(monkeypatch)
    monkeypatch.setattr(utils.tiktoken, 'get_encoding',
                        lambda name: loads.append(name) or _FakeEncoding(name))

    first = utils._get_tiktoken_encoding('cl100k_base')
    other = utils._get_tiktoken_encoding('o200k_base')
    again = utils._get_tiktoken_encoding('cl100k_base')

    assert loads == ['cl100k_base', 'o200k_base'], "one load per name, no reload thrash"
    assert again is first and first.name == 'cl100k_base'
    assert other.name == 'o200k_base'


def test_tiktoken_cache_under_two_concurrent_names(monkeypatch):
    loads = []
    loads_lock = threading.Lock()

    def slow_get_encoding(name):
        with loads_lock:
            loads.append(name)
        time.sleep(0.01)
        return _FakeEncoding(name)

    _reset_tiktoken_cache(monkeypatch)
    monkeypatch.setattr(utils.tiktoken, 'get_encoding', slow_get_encoding)

    results = []
    barrier = threading.Barrier(2)

    def worker(name):
        barrier.wait()
        for _ in range(50):
            results.append((name, utils._get_tiktoken_encoding(name).name))

    threads = [threading.Thread(target=worker, args=(name,))
               for name in ('cl100k_base', 'o200k_base')]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert all(want == got for want, got in results), \
        f"every caller must get its own encoding, got: {sorted(set(results))}"
    assert sorted(loads) == ['cl100k_base', 'o200k_base'], \
        f"each name loads once, got loads={loads}"
    assert len(loads) == 2


# ---------------------------------------------------------------------------
# DEF-M5: llm_logger — whole-line JSON under a lock
# ---------------------------------------------------------------------------

_LOG_CALL = dict(
    stage="INITIAL", role="translate", model="m", temperature=0.7,
    duration_ms=1, tokens_input=1, tokens_output=1, tokens_total=2,
    prompt_system="s", prompt_user="u", response="r",
)


def test_llm_logger_parallel_writes_stay_valid_json_lines(tmp_path):
    logger = LLMLogger(log_dir=str(tmp_path))
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # force frequent thread switches mid-write
    try:
        barrier = threading.Barrier(2)

        def worker(k):
            barrier.wait()
            for i in range(100):
                logger.log_call(**{**_LOG_CALL,
                                   "response": f"поток {k}, строка {i} " + "я" * 6000})

        threads = [threading.Thread(target=worker, args=(k,)) for k in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    finally:
        sys.setswitchinterval(old_interval)

    today = datetime.now().strftime("%Y-%m-%d")
    lines = (tmp_path / f"llm_calls_{today}.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200, f"expected 200 lines, got {len(lines)}"
    entries = [json.loads(line) for line in lines]  # every line is valid JSON
    assert all(e["stage"] == "INITIAL" for e in entries)
    responses = {e["response"].split(",")[0] for e in entries}
    assert responses == {"поток 1", "поток 2"}


# ---------------------------------------------------------------------------
# DEF-M7: unique temp file + cleanup (dict_clean.write_atomic)
# ---------------------------------------------------------------------------

def test_write_atomic_cleans_up_its_temp_file_on_failure(tmp_path, monkeypatch):
    out = tmp_path / 'book.clean.dic'

    def failing_replace(src, dst):
        raise OSError('disk full')

    monkeypatch.setattr(os, 'replace', failing_replace)
    with pytest.raises(OSError):
        dict_clean.write_atomic(out, 'content')

    assert not out.exists()
    assert list(tmp_path.iterdir()) == [], \
        f"no temp garbage left behind: {[p.name for p in tmp_path.iterdir()]}"


def test_write_atomic_concurrent_writers_do_not_clobber_each_other(tmp_path, monkeypatch):
    out = tmp_path / 'book.clean.dic'
    a_text, b_text = 'A' * 20000, 'B' * 20000
    first_replace_started = threading.Event()
    real_replace = os.replace
    calls = []

    def orchestrated_replace(src, dst):
        calls.append(str(src))
        if len(calls) == 1:
            first_replace_started.set()
            time.sleep(0.5)  # let the second writer get in before the first rename
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', orchestrated_replace)
    errors = []

    def worker(text):
        try:
            dict_clean.write_atomic(out, text)
        except Exception as e:
            errors.append(repr(e))

    t1 = threading.Thread(target=worker, args=(a_text,))
    t1.start()
    assert first_replace_started.wait(10), "first writer must reach its rename"
    t2 = threading.Thread(target=worker, args=(b_text,))
    t2.start()
    t1.join(30)
    t2.join(30)

    assert errors == [], f"both writers must succeed, got: {errors}"
    assert out.read_text(encoding='utf-8') in (a_text, b_text), \
        "the output must be one writer's content, whole"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != out.name]
    assert leftovers == [], f"no temp garbage left behind: {leftovers}"


# ---------------------------------------------------------------------------
# DEF-M7: unique temp file in VocabularyManager.build_dictionary
# ---------------------------------------------------------------------------

def test_build_dictionary_is_not_confused_by_a_foreign_dot_building_file(tmp_path, monkeypatch):
    """Another process using the old fixed `.building` name must not end up
    inside our dictionary (our temp file has a unique name now)."""
    fake_ner = MagicMock()
    fake_ner.create_dictionary_from_text.return_value = [("Alice", "PERSON", "")]
    monkeypatch.setattr(vm, 'ner_module', fake_ner)
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.config, 'max_len_chunk', 100)

    dict_file = tmp_path / "book.dic"
    zombie_name = str(dict_file) + '.building'

    def colliding_llm(*args):
        # as if another process's build were writing to the old fixed temp name
        with open(zombie_name, 'w', encoding='utf-8') as f:
            f.write("Foreign = junk, TERM, ,\n")
        return json.dumps([{"source": "Alice", "target": "Алиса", "category": "PERSON"}])

    monkeypatch.setattr('src.utils.vocabulary', colliding_llm)
    manager = vm.VocabularyManager(str(tmp_path / "book.fb2"), dict_file=str(dict_file))
    manager.build_dictionary("text")

    content = dict_file.read_text(encoding='utf-8')
    assert "junk" not in content, "the foreign .building file must not leak into the dictionary"
    assert "Alice = Алиса" in content


def test_failed_build_cleans_up_its_temp_file(tmp_path, monkeypatch):
    fake_ner = MagicMock()
    fake_ner.create_dictionary_from_text.return_value = [("Alice", "PERSON", "")]
    monkeypatch.setattr(vm, 'ner_module', fake_ner)
    monkeypatch.setattr(vm.config, 'ner_opt', True)
    monkeypatch.setattr(vm.config, 'max_len_chunk', 100)

    def failing_llm(*args):
        raise ConnectionError("LLM down")

    monkeypatch.setattr('src.utils.vocabulary', failing_llm)
    manager = vm.VocabularyManager(str(tmp_path / "book.fb2"), dict_file=str(tmp_path / "book.dic"))

    with pytest.raises(ConnectionError):
        manager.build_dictionary("text")

    assert os.listdir(tmp_path) == [], \
        f"no .dic and no temp files after a failed build: {os.listdir(tmp_path)}"


# ---------------------------------------------------------------------------
# DEF-M8: skipped-line counter in _load_from_file
# ---------------------------------------------------------------------------

def test_load_from_file_reports_skipped_lines(tmp_path, caplog):
    dic = tmp_path / 'book.dic'
    dic.write_text(
        "# comment\n"
        "Alice = Алиса, PERSON, she,\n"
        "no separator line\n"
        "Bob = Боб, PERSON, he,\n"
        "Broken = , PERSON, ,\n",
        encoding='utf-8')

    manager = vm.VocabularyManager.__new__(vm.VocabularyManager)
    manager.dict_file = str(dic)
    with caplog.at_level('WARNING'):
        vocab = manager._load_from_file()

    assert {e.source for e in vocab.values()} == {'Alice', 'Bob'}, \
        "good lines still load when neighbours are broken"
    assert "skipped 2" in caplog.text, f"the two unparsable lines must be counted: {caplog.text!r}"


# ---------------------------------------------------------------------------
# DEF-M10: dict_convert JSON parsing (json.loads first, slice fallback)
# ---------------------------------------------------------------------------

def _reply_client(text):
    client = MagicMock()
    reply = MagicMock()
    reply.choices[0].message.content = text
    client.chat.completions.create.return_value = reply
    return client


def _translate_batch(client, batch):
    monkeypatch_values = None
    return dict_convert.translate_batch(client, 'Russian', batch, 'Russian', 'Russian')


def test_translate_batch_parses_the_json_inside_prose(monkeypatch):
    monkeypatch.setattr(dict_convert.config, 'nothink_proofread', False)
    client = _reply_client('Готово, словарь во вложении:\n'
                           '{"terms": [{"id": 0, "target": "Иван"}]}\nКонец.')
    result = _translate_batch(client, [('Ivan', None, 'PERSON')])
    assert result == {0: 'Иван'}


def test_translate_batch_does_not_raise_on_a_braced_comment(monkeypatch, caplog):
    """A '{...}' inside a comment used to make the greedy regex match garbage
    and the JSONDecodeError escaped as if it were a network failure (retried
    3x). Now the answer is parsed locally (or reported), never raised."""
    monkeypatch.setattr(dict_convert.config, 'nothink_proofread', False)
    client = _reply_client('{"terms": [{"id": 0, "target": "Иван"}]} // черновик {v2}')
    with caplog.at_level('WARNING'):
        result = _translate_batch(client, [('Ivan', None, 'PERSON')])  # must not raise
    assert result == {}
    assert "parseable JSON" in caplog.text or "No parseable" in caplog.text


def test_translate_batch_warns_when_the_answer_has_no_json(monkeypatch, caplog):
    monkeypatch.setattr(dict_convert.config, 'nothink_proofread', False)
    client = _reply_client('Извините, не могу перевести эти термины.')
    with caplog.at_level('WARNING'):
        result = _translate_batch(client, [('Ivan', None, 'PERSON')])
    assert result == {}
    assert "parseable JSON" in caplog.text or "No parseable" in caplog.text


# ---------------------------------------------------------------------------
# DEF-M20: epub_repair — corrupt OPF manifest is not a silent []
# ---------------------------------------------------------------------------

_CONTAINER = (
    '<?xml version="1.0"?>\n'
    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)
_CORRUPT_OPF = 'this manifest was corrupted by a bad download; no xml structure here'
_EMPTY_MANIFEST_OPF = (
    '<?xml version="1.0"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
    '<manifest></manifest></package>'
)


def _make_epub(tmp_path, opf_content, name='book.epub'):
    path = tmp_path / name
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', _CONTAINER)
        zf.writestr('OEBPS/content.opf', opf_content)
        zf.writestr('OEBPS/ch1.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>')
    return str(path)


def test_corrupt_opf_manifest_returns_none_not_an_empty_list(tmp_path):
    epub = _make_epub(tmp_path, _CORRUPT_OPF)
    with zipfile.ZipFile(epub) as zf:
        assert _get_xhtml_files_from_opf(zf, 'OEBPS/content.opf') is None


def test_a_valid_empty_manifest_is_still_an_empty_list(tmp_path):
    epub = _make_epub(tmp_path, _EMPTY_MANIFEST_OPF)
    with zipfile.ZipFile(epub) as zf:
        assert _get_xhtml_files_from_opf(zf, 'OEBPS/content.opf') == []


def test_validate_epub_reports_an_unreadable_manifest(tmp_path):
    epub = _make_epub(tmp_path, _CORRUPT_OPF)
    errors = validate_epub(epub)
    assert any('Cannot parse OPF manifest' in e for e in errors), \
        f"a corrupt manifest must be a visible error, got: {errors}"
