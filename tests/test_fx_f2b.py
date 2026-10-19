"""F2 stream B: major fixes M12-M17, M21-M24 (ner, fb2, txt).

Red/green tests: each one fails on the pre-fix code and passes after the fix.
"""
import logging
import os
import sys
import threading
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# M16: word-boundary in detect_mentions ('Ana' must not fire inside 'banana')
# ---------------------------------------------------------------------------

def test_m16_ana_not_matched_inside_banana():
    from src.character_registry import CharacterRegistry
    registry = CharacterRegistry()
    ana = registry.add_character("Ana", "Ана", "she")
    mentioned = registry.detect_mentions("I ate a banana and an apple.", 0, 0)
    assert mentioned == []
    assert ana.get_mention_count() == 0


def test_m16_ana_still_matched_as_whole_word():
    from src.character_registry import CharacterRegistry
    registry = CharacterRegistry()
    ana = registry.add_character("Ana", "Ана", "she")
    mentioned = registry.detect_mentions("Ana went home. Then ana came back.", 0, 0)
    assert [c.name for c in mentioned] == ["Ana"]
    assert ana.get_mention_count() == 1


def test_m16_tim_not_matched_inside_estimate():
    from src.character_registry import CharacterRegistry
    registry = CharacterRegistry()
    tim = registry.add_character("Tim", "Тим", "he")
    assert registry.detect_mentions("Please estimate the cost.", 0, 0) == []
    assert tim.get_mention_count() == 0


def test_m16_hyphen_and_cjk():
    from src.character_registry import CharacterRegistry
    registry = CharacterRegistry()
    ana = registry.add_character("Ana", "", "she")
    # a hyphen is a word-internal character: 'Ana-maria' is another name
    assert registry.detect_mentions("Ana-maria waved.", 0, 0) == []
    assert ana.get_mention_count() == 0
    # CJK has no word boundaries: substring match stays
    li = registry.add_character("莉", "Ли", "she")
    assert registry.detect_mentions("她被叫作莉娜，她笑了。", 0, 0) == [li]


# ---------------------------------------------------------------------------
# M17: substring merge must respect token boundaries ('Тим' kept next to 'Тимоти')
# ---------------------------------------------------------------------------

def test_m17_tim_and_timothy_both_kept():
    from src.ner import _merge_overlapping_entities
    entities = [("Тимоти", "PERSON", 3), ("Тим", "PERSON", 5)]
    result = _merge_overlapping_entities(entities)
    names = {r[0] for r in result}
    assert names == {"Тимоти", "Тим"}


def test_m17_substring_containment_still_merges():
    """A whole-token containment ('John' inside 'John Smith') still merges."""
    from src.ner import _merge_overlapping_entities
    entities = [("John Smith", "PERSON", 2), ("John", "PERSON", 10)]
    result = _merge_overlapping_entities(entities)
    assert len(result) == 1
    assert result[0][0] == "John Smith"


def test_m17_inflected_form_still_merges():
    """'Centurion' inside 'Centurions' is an inflection, not a different name."""
    from src.ner import _merge_overlapping_entities
    entities = [("Centurions", "ORG", 4), ("centurion", "ORG", 2)]
    result = _merge_overlapping_entities(entities)
    assert len(result) == 1
    assert result[0][0].lower() == "centurions"


def test_m17_covered_by_helper_boundaries():
    from src.ner import _covered_by
    assert not _covered_by("Тим", "Тимоти")
    assert _covered_by("Тимоти", "Тимоти Крюгер")
    assert _covered_by("Centurion", "Centurions")
    assert not _covered_by("Ana", "banana")
    assert not _covered_by("Gant", "Gantry")
    # CJK: substring still counts
    assert _covered_by("莉", "莉娜")


# ---------------------------------------------------------------------------
# M12: make_vocab must warn + count failed chunks (no more silent skip)
# ---------------------------------------------------------------------------

class _BoomNlp:
    def __init__(self):
        self.calls = 0

    def __call__(self, text, disable=None):
        self.calls += 1
        raise RuntimeError("nlp blew up")


def test_m12_make_vocab_warns_and_counts_failed_chunks(monkeypatch, caplog):
    from src import ner
    boom = _BoomNlp()
    monkeypatch.setattr(ner, '_get_nlp', lambda *a, **k: boom)
    monkeypatch.setattr(ner.lexicon, 'get_stop_words', lambda lang: frozenset())
    monkeypatch.setattr(ner, 'known_words', lambda words: set())
    monkeypatch.setattr(ner, '_lemma_keys', lambda nlp, terms: {})
    with caplog.at_level(logging.WARNING, logger="src.ner"):
        ner.make_vocab("x" * 150000)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("2" in w and "chunk" in w.lower() for w in warnings), warnings


def test_m12_make_vocab_no_warning_when_no_chunks_fail(monkeypatch, caplog):
    from src import ner

    class _Ok:
        def __call__(self, text, disable=None):
            return _EmptyDoc()

    monkeypatch.setattr(ner, '_get_nlp', lambda *a, **k: _Ok())
    monkeypatch.setattr(ner.lexicon, 'get_stop_words', lambda lang: frozenset())
    monkeypatch.setattr(ner, 'known_words', lambda words: set())
    monkeypatch.setattr(ner, '_lemma_keys', lambda nlp, terms: {})
    monkeypatch.setattr(ner.config, 'dict_frequent_words', False)
    with caplog.at_level(logging.WARNING, logger="src.ner"):
        ner.make_vocab("short text")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class _EmptyDoc:
    """Minimal spaCy doc stand-in: no ents, no tokens."""
    ents = ()
    lang_ = 'en'

    def __iter__(self):
        return iter(())


# ---------------------------------------------------------------------------
# M13: create_series_vocab must report failed chunks
# ---------------------------------------------------------------------------

def test_m13_series_vocab_reports_failed_chunks(monkeypatch, tmp_path, capsys):
    from src import ner

    book = tmp_path / "book.txt"
    book.write_text("Once upon a time. " * 9000, encoding='utf-8')

    class _Boom:
        def __call__(self, text, disable=None):
            raise RuntimeError("chunk blew up")

        def pipe(self, texts, batch_size=None, disable=None):
            return iter(())

    monkeypatch.setattr(ner, '_get_nlp', lambda *a, **k: _Boom())
    monkeypatch.setattr(ner.lexicon, 'get_stop_words', lambda lang: frozenset())
    monkeypatch.setattr(ner.config, 'dict_frequent_words', False)
    ner.create_series_vocab(str(tmp_path), output_file="series.dic")
    out = capsys.readouterr().out
    assert "chunks failed" in out.lower(), out


# ---------------------------------------------------------------------------
# M14: phrase-vector cache key must include the model
# ---------------------------------------------------------------------------

def test_m14_phrase_cache_keyed_by_model(monkeypatch):
    from src import ner
    import numpy as np

    class _FakeDoc:
        def __init__(self, v):
            self._vector = np.asarray(v, dtype=np.float32)

        @property
        def vector(self):
            return self._vector

        @property
        def vector_norm(self):
            return float(np.linalg.norm(self._vector))

    class _NlpA:
        def pipe(self, texts, disable=None):
            return [_FakeDoc([1.0, 0.0]) for _ in texts]

    class _NlpB:
        def pipe(self, texts, disable=None):
            return [_FakeDoc([0.0, 1.0]) for _ in texts]

    ner._PHRASE_VECTOR_CACHE.clear()
    monkeypatch.setattr(ner.config, 'nermodel', 'model_a')
    v1 = ner._get_phrase_vector("aaa", _NlpA())
    monkeypatch.setattr(ner.config, 'nermodel', 'model_b')
    v2 = ner._get_phrase_vector("aaa", _NlpB())
    assert v1 is not None and v2 is not None and not np.array_equal(v1, v2)
    # same model again -> cached
    v3 = ner._get_phrase_vector("aaa", _NlpB())
    assert np.array_equal(v2, v3)


# ---------------------------------------------------------------------------
# M15: locks around the nlp cache and the shared nlp call
# ---------------------------------------------------------------------------

def test_m15_nlp_cache_single_load_under_threads(monkeypatch):
    """Two threads racing for the same missing model: one load, not two."""
    from src import ner

    class _FakeModel:
        max_length = 0

    entered = []
    release = threading.Event()

    def fake_load(name):
        entered.append(name)
        release.wait(timeout=5)
        return _FakeModel()

    monkeypatch.setattr(ner, 'load_spacy_model', fake_load)
    ner._nlp_cache.pop('m1', None)

    t1 = threading.Thread(target=lambda: ner._get_nlp('m1'))
    t1.start()
    time.sleep(0.4)  # t1 is inside the loader now
    t2 = threading.Thread(target=lambda: ner._get_nlp('m1'))
    t2.start()
    time.sleep(0.4)  # without a lock t2 is inside the loader too
    release.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    try:
        assert entered == ['m1'], f"model loaded {len(entered)} times"
        assert 'm1' in ner._nlp_cache
    finally:
        ner._nlp_cache.pop('m1', None)


def test_m15_concurrent_match_smoke(monkeypatch):
    from src import ner
    import numpy as np

    class _Tok:
        is_alpha = True
        is_punct = False
        is_space = False
        lemma_ = ''
        text = 'aaa'

        def __init__(self):
            self._v = np.asarray([1.0, 0.0], dtype=np.float32)

        @property
        def vector(self):
            return self._v

        @property
        def vector_norm(self):
            return 1.0

    class _FakeDoc:
        def __init__(self, v):
            self._vector = np.asarray(v, dtype=np.float32)

        @property
        def vector(self):
            return self._vector

        @property
        def vector_norm(self):
            return float(np.linalg.norm(self._vector))

        def __iter__(self):
            return iter([_Tok()])

    class _Nlp:
        def __call__(self, text, disable=None):
            return _FakeDoc([1.0, 0.0])

        def pipe(self, texts, disable=None):
            return [_FakeDoc([1.0, 0.0]) for _ in texts]

    monkeypatch.setattr(ner, '_get_nlp', lambda *a, **k: _Nlp())
    ner._PHRASE_VECTOR_CACHE.clear()
    ner._UNUSABLE_MATCH_MODELS.clear()

    errors = []
    results = []
    vocab = {'qqq': {'en': 'qqq'}}

    def run():
        for _ in range(10):
            try:
                results.append(tuple(ner._match_vocab_terms("aaa bbb", vocab, 'en', 0.5, 64, np)))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, errors
    assert len(results) == 40


# ---------------------------------------------------------------------------
# M21: comments must not break parse_xml slicing
# ---------------------------------------------------------------------------

_FB2_WITH_COMMENT_TRAPS = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
    '<description><title-info><book-title>T</book-title></title-info></description>\n'
    '<!-- <body> -->\n'
    '<body><section><p>Hello</p></section></body>\n'
    '<!-- </body> -->\n'
    '</FictionBook>')


def test_m21_comment_body_trap_does_not_break_slicing(tmp_path):
    from src.fb2_handler import parse_xml
    path = tmp_path / "book.fb2"
    path.write_text(_FB2_WITH_COMMENT_TRAPS, encoding='utf-8')
    body, header, footer = parse_xml(str(path))
    assert body.strip() == '<section><p>Hello</p></section>'
    assert 'Hello' not in header and 'Hello' not in footer
    assert '</FictionBook>' in footer


def test_m21_two_bodies_flag(tmp_path, caplog):
    """A notes body must not silently flow into the footer unreported."""
    from src.fb2_handler import parse_xml
    fb2 = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
           '<description><title-info><book-title>T</book-title></title-info></description>\n'
           '<body><section><p>Main</p></section></body>\n'
           '<body name="notes"><section><p>Note</p></section></body>\n'
           '</FictionBook>')
    path = tmp_path / "two.fb2"
    path.write_text(fb2, encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger="src.fb2_handler"):
        body, header, footer = parse_xml(str(path))
    assert "Main" in body
    assert "Note" in footer  # placement unchanged (product decision pending)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("body" in w.lower() for w in warnings), warnings


def test_m21_no_false_warning_for_single_body(tmp_path, caplog):
    from src.fb2_handler import parse_xml
    path = tmp_path / "one.fb2"
    path.write_text(_FB2_WITH_COMMENT_TRAPS, encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger="src.fb2_handler"):
        parse_xml(str(path))
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert not [w for w in warnings if 'body' in w.lower()], warnings


# ---------------------------------------------------------------------------
# M22: U+FFFD replacement must produce a warning
# ---------------------------------------------------------------------------

def test_m22_replacement_chars_warn(tmp_path, caplog, monkeypatch):
    from src import fb2_handler
    path = tmp_path / "weird.fb2"
    # 0x98 is undefined in cp1251 -> strict decode fails -> errors='replace'
    path.write_bytes(b'\x98 text')
    monkeypatch.setattr(fb2_handler.chardet, 'detect', lambda raw: {'encoding': 'cp1251'})
    with caplog.at_level(logging.WARNING, logger="src.fb2_handler"):
        content = fb2_handler._read_file_with_encoding_fallback(str(path))
    assert '\ufffd' in content
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any('replacement' in w.lower() for w in warnings), warnings


def test_m22_clean_utf8_no_warning(tmp_path, caplog):
    from src.fb2_handler import _read_file_with_encoding_fallback
    path = tmp_path / "clean.fb2"
    path.write_bytes('Привет мир'.encode('utf-8'))
    with caplog.at_level(logging.WARNING, logger="src.fb2_handler"):
        content = _read_file_with_encoding_fallback(str(path))
    assert content == 'Привет мир'
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# M23: TXT -> FB2 must be schema-valid
# ---------------------------------------------------------------------------

def test_m23_parse_txt_output_is_schema_valid(tmp_path):
    from src.txt_handler import parse_txt
    from src.xmlcheck import validate_fb2
    path = tmp_path / "story.txt"
    path.write_text("Chapter 1\n\nHello world. This is a test.\n", encoding='utf-8')
    body, header, footer = parse_txt(str(path))
    assert validate_fb2(header + body + footer) == []


def test_m23_plain_txt_is_schema_valid(tmp_path):
    from src.txt_handler import parse_txt
    from src.xmlcheck import validate_fb2
    path = tmp_path / "plain.txt"
    path.write_text("Just one line of prose.\n", encoding='utf-8')
    body, header, footer = parse_txt(str(path))
    assert validate_fb2(header + body + footer) == []


# ---------------------------------------------------------------------------
# M24: comments with tags must be verbatim in repair, output well-formed
# ---------------------------------------------------------------------------

def test_m24_comment_with_body_tags_stays_verbatim():
    from src.fb2_structure import repair_fragment
    frag = '<section><p>before</p><!-- <body> --><p>example</p></section>'
    out = repair_fragment(frag, keep_sections=True, strip_unknown=False)
    assert '<!-- <body> -->' in out
    assert '</body>' not in out  # comment content did not become markup


def test_m24_repair_fb2_output_well_formed_with_comments():
    from lxml import etree
    from src.fb2_repair import repair_fb2
    doc = ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
           '<description/>'
           '<!-- <body> --><body><section><p>abc</p></section></body><p>tail</p>'
           '</FictionBook>')
    repaired, repairs = repair_fb2(doc)
    assert '<!-- <body> -->' in repaired
    etree.fromstring(repaired.encode('utf-8'))  # raises if not well-formed


def test_m24_comment_inside_body_verbatim():
    from lxml import etree
    from src.fb2_repair import repair_fb2
    doc = ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
           '<description/><body><section><p>abc</p><!-- <p>commented</p> --></section></body>'
           '</FictionBook>')
    repaired, _ = repair_fb2(doc)
    assert '<!-- <p>commented</p> -->' in repaired
    etree.fromstring(repaired.encode('utf-8'))


def test_m24_well_formed_input_with_comment_unchanged_where_text_equal():
    """A well-formed body with a comment: repair must not reject it as text-changing."""
    from src.fb2_repair import repair_fb2
    doc = ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
           '<description/><body><!-- <body> --><section><p>abc</p></section></body>'
           '</FictionBook>')
    repaired, _ = repair_fb2(doc)
    assert '<!-- <body> -->' in repaired
