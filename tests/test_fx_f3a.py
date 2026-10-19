"""Targeted tests for the uncommitted DEF-N* fixes (review f3a).

Covers: DEF-N1 (num_tokens fallback), DEF-N2 (dropped candidate warning),
DEF-N4 (html_to_paragraphs double escaping), DEF-N5 (metrics thread safety),
DEF-N6 (empty-choices response), DEF-N11 (FB2 rejected in calibre pipeline),
DEF-N12 (dc:identifier ISBN scan), plus the <p>-tag detection fix in
p_tags_processor.
"""
import logging
import os
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
import src.utils as u
from src.html_text import html_to_paragraphs
from src.p_tags_processor import _count_p_tags, _has_p_tags


# ---------------------------------------------------------------- DEF-N4
def test_html_to_paragraphs_doubly_escaped():
    # '<p>One</p><p>Two</p>' escaped twice
    value = '&amp;lt;p&amp;gt;One&amp;amp;lt;/p&amp;amp;gt;&amp;amp;lt;p&amp;amp;gt;Two&amp;amp;lt;/p&amp;amp;gt;'
    paras = html_to_paragraphs(value)
    assert all('&lt;' not in p and '&gt;' not in p for p in paras)


def test_html_to_paragraphs_escaped_once():
    paras = html_to_paragraphs('&lt;p&gt;Hello&lt;/p&gt;&lt;p&gt;World&lt;/p&gt;')
    assert paras == ['Hello', 'World']


def test_html_to_paragraphs_mixed_escaped_and_literal():
    paras = html_to_paragraphs('<p>Real tag</p>&lt;p&gt;Escaped one&lt;/p&gt;')
    assert 'Real tag' in paras
    assert 'Escaped one' in paras
    assert all('&lt;p&gt;' not in p and '&lt;' not in p for p in paras)


# ------------------------------------------------------ p_tags_processor
@pytest.mark.parametrize("text", ['<p class="x">a</p>', '<P>hi</P>', '</P>only close'])
def test_has_p_tags_case_and_attributes(text):
    has_open, has_close = _has_p_tags(text)
    assert has_close is True
    if 'only close' not in text:
        assert has_open is True


def test_has_p_tags_pre_is_not_p():
    assert _has_p_tags('<pre>code</pre>') == (False, False)
    assert _count_p_tags('<pre>code</pre>') == (0, 0)


def test_count_p_tags_with_attributes_and_case():
    text = '<p class="a"><P>x</P><p>y</p>'
    opens, closes = _count_p_tags(text)
    assert opens == 3
    assert closes == 2


# ---------------------------------------------------------------- DEF-N12
def _opf(identifiers):
    ids = "\n".join(
        f'    <dc:identifier id="BookId">{i}</dc:identifier>' for i in identifiers
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<metadata>'
        '<dc:title>Some Book</dc:title>'
        '<dc:language>en</dc:language>'
        f'{ids}'
        '</metadata></package>'
    )


def test_isbn_uuid_first_urn_isbn_second_wins():
    md = cp.extract_metadata_from_opf(
        _opf(['urn:uuid:88284b24-2c4a-4c3e-8b1f-0d5a9e7c1234',
              'urn:isbn:9783161484104'])
    )
    assert md.get('isbn') == 'urn:isbn:9783161484104'


def test_isbn_valid_without_urn_prefix():
    md = cp.extract_metadata_from_opf(_opf(['urn:uuid:deadbeef',
                                            '9783161484104']))
    assert md.get('isbn') == '9783161484104'


def test_isbn10_with_hyphens_without_urn_prefix():
    md = cp.extract_metadata_from_opf(_opf(['urn:uuid:deadbeef',
                                            '0-306-40615-2']))
    assert md.get('isbn') == '0-306-40615-2'


def test_isbn_invalid_values_rejected():
    md = cp.extract_metadata_from_opf(
        _opf(['urn:uuid:88284b24-2c4a-4c3e', 'not-an-isbn', '123'])
    )
    assert md.get('isbn', '') == ''


# ---------------------------------------------------------------- DEF-N11
def test_fb2_input_rejected_by_calibre_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, 'check_calibre_installed', lambda: True)
    fb2 = tmp_path / 'book.fb2'
    fb2.write_text('<?xml version="1.0"?><FictionBook></FictionBook>',
                   encoding='utf-8')
    with pytest.raises(ValueError, match='Unsupported input format'):
        cp.convert_to_markdown(str(fb2))


# ----------------------------------------------------------------- DEF-N5
def test_metrics_report_under_concurrency():
    m = u.TranslationMetrics()
    n_threads, n_iters = 6, 300
    errors = []
    stop = threading.Event()

    def worker(idx):
        try:
            for j in range(n_iters):
                m.log_success(10)
                if j % 3 == 0:
                    m.log_retry(5, 'test')
                m.log_mixed_words([f'w{idx}{j}'])
                issue = SimpleNamespace(name=f'Name{idx}', gender='f')
                m.log_gender([issue], 1)
                m.log_synopsis_gender(f'Syn{idx}', 'm')
        except Exception as e:  # noqa: BLE001 - the point is to capture any crash
            errors.append(e)

    def reporter():
        try:
            while not stop.is_set():
                rep = m.get_report()
                assert rep['successful_translations'] >= 0
                m.print_report()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    report_thread = threading.Thread(target=reporter)
    report_thread.start()
    workers = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    stop.set()
    report_thread.join()

    assert errors == []
    rep = m.get_report()
    assert rep['successful_translations'] == n_threads * n_iters
    assert rep['total_tokens'] == n_threads * n_iters * 10


# ----------------------------------------------------------------- DEF-N1
def test_num_tokens_unknown_encoding_falls_back():
    n1 = u.num_tokens_in_string('hello world', encoding_name='no-such-enc-xyz')
    n2 = u.num_tokens_in_string('hello world')
    assert n1 > 0
    assert n1 == n2  # both go through cl100k_base


# ----------------------------------------------------------------- DEF-N2
def test_malformed_candidate_line_is_warned(caplog):
    response = (
        'A summary.\n'
        '<genders>\n'
        'Alice | Алиса | female\n'
        'Bob | Боб\n'  # PERSON line missing the gender field
        '</genders>'
    )
    source = 'Alice and Bob met at the fair.'
    with caplog.at_level(logging.WARNING):
        _, candidates = u.extract_dictionary_candidates(response, source)
    names = [c.get('source') for c in candidates]
    assert 'Alice' in names
    assert 'Bob' not in names
    assert any('dropped' in r.message and 'PERSON' in r.message
               for r in caplog.records)


# ----------------------------------------------------------------- DEF-N6
def test_llm_response_without_choices_raises(monkeypatch):
    svc = u.LLMService()
    empty_response = SimpleNamespace(choices=[])
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: empty_response)
        )
    )
    monkeypatch.setattr(svc, 'get_client',
                        lambda role: (fake_client, 'test-model', 0.3))
    with pytest.raises(ValueError, match='no choices'):
        svc.complete(u.LLMRole.TRANSLATE, 'sys', 'user')
