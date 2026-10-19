"""F3b minor quick-win fixes (fx-f3b): DEF-N34/N36/N38/N41/N42, the
huge_tree follow-up of DEF-C6, and the stage-1 extension of
convert_html_to_fb2_section (DEF-M19)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bs4 import BeautifulSoup

import src.epub_repair as er
import src.xmlcheck as xc
import src.xml_utils as xu
from src.epub_handler import convert_html_to_fb2_section
from src.fb2_handler import add_annotation_credit, parse_xml
from src.txt_handler import _is_chapter_heading
from src.utils import CREDIT_LINE

_FB2_HEADER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
    '<description><title-info><genre>prose_classic</genre>'
    '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
    '<book-title>T</book-title><lang>en</lang></title-info>'
    '<document-info><author><nickname>t</nickname></author>'
    '<date value="2024-01-01">2024</date><id>x-1</id><version>1.0</version>'
    '</document-info></description>'
)
_NS = 'http://www.gribuser.ru/xml/fictionbook/2.0'


# ---------------------------------------------------------------------------
# DEF-N34: epub_repair.validate_epub renamed to validate_epub_structure
# ---------------------------------------------------------------------------

def test_validate_epub_renamed():
    assert hasattr(er, 'validate_epub_structure')
    assert not hasattr(er, 'validate_epub')


# ---------------------------------------------------------------------------
# DEF-N36: every xmlns in the body fragment is stripped, not just the first
# ---------------------------------------------------------------------------

def test_parse_xml_strips_all_namespaces(tmp_path):
    book = (_FB2_HEADER
            + f'<body><section xmlns="{_NS}"><p>one</p></section>'
            + f'<p xmlns="{_NS}">two</p></body></FictionBook>')
    path = tmp_path / 'book.xml'
    path.write_text(book, encoding='utf-8')
    body, header, footer = parse_xml(str(path))
    assert 'xmlns' not in body
    assert '<p>one</p>' in body and '<p>two</p>' in body


# ---------------------------------------------------------------------------
# DEF-N38: opaque "General Validation Error" now names the exception type
# ---------------------------------------------------------------------------

def test_general_validation_error_names_type():
    errors = xc.validate_fb2(b'not a string')  # AttributeError, not XMLSyntaxError
    assert len(errors) == 1
    assert 'General Validation Error: AttributeError' in errors[0]


# ---------------------------------------------------------------------------
# DEF-N41: only the trailing paragraph can be an earlier credit
# ---------------------------------------------------------------------------

def _header_with_annotation(paras):
    ann = '<annotation>' + ''.join(f'<p>{p}</p>' for p in paras) + '</annotation>'
    return (_FB2_HEADER.replace('</title-info>', ann + '</title-info>'))


def test_credit_mid_annotation_survives():
    header = _header_with_annotation(['Read my book!', CREDIT_LINE, 'real prose after'])
    out = add_annotation_credit(header)
    # the mid credit-looking paragraph is kept; the new credit goes last
    assert out.count(f'<p>{CREDIT_LINE}</p>') == 2
    assert 'real prose after</p>' in out
    ann = out[out.index('<annotation>'):out.index('</annotation>')]
    assert ann.rstrip().endswith(f'real prose after</p><p>{CREDIT_LINE}</p>')


def test_credit_replaces_trailing_previous_credit():
    header = _header_with_annotation(['intro', CREDIT_LINE])
    out = add_annotation_credit(header)
    assert out.count(CREDIT_LINE) == 1  # idempotent: old trailing credit replaced
    assert out.count('<p>' + CREDIT_LINE + '</p>') == 1


# ---------------------------------------------------------------------------
# DEF-N42: tightened TXT heading heuristics
# ---------------------------------------------------------------------------

def test_cjk_marker_inside_prose_not_a_heading():
    assert not _is_chapter_heading('第3章の話に出てくる人物はみんな個性的だ', None)
    assert not _is_chapter_heading('20화부터 시작하는 이야기', None)
    assert _is_chapter_heading('第3章 冒険', None)
    assert _is_chapter_heading('제20화', None)


def test_separator_promotion_needs_short_non_sentence_line():
    assert _is_chapter_heading('Mysterious Beginnings', '========')
    assert not _is_chapter_heading('And then she went home.', '========')
    assert not _is_chapter_heading('x' * 130, None)  # oversized: prose


# ---------------------------------------------------------------------------
# DEF-C6 follow-up: huge_tree on the remaining XXE-safe parsers
# ---------------------------------------------------------------------------

def test_safe_parser_has_huge_tree_and_tolerates_big_text():
    from lxml import etree
    # XMLParser exposes no .huge_tree attribute; the functional check is
    # that an 11 MB text node parses without the libxml2 "resource huge"
    # error (default limits raise XMLSyntaxError without huge_tree).
    big = ('<html><body><p>' + 'A' * 11_000_000 + '</p></body></html>').encode('utf-8')
    etree.fromstring(big, xu.get_safe_xml_parser())  # must not raise


def test_validate_xml_tolerates_big_inline_content():
    big = ('<html><body><img src="data:image/png;base64,' + 'A' * 11_000_000
           + '"/></body></html>').encode('utf-8')
    assert er._validate_xml(big, 'chapter.xhtml') == []


# ---------------------------------------------------------------------------
# DEF-M19 stage 1: convert_html_to_fb2_section lists/blockquote/logged drops
# ---------------------------------------------------------------------------

def test_lists_blockquote_and_div_text_produce_valid_fb2():
    html = ('<html><body><h2>Gl</h2><p>Hello <b>bold</b>.</p>'
            '<ul><li>one <i>it</i></li><li>two</li></ul>'
            '<ol><li>first</li><li>second</li></ol>'
            '<blockquote>Quoted &amp; words<p>nested para</p></blockquote>'
            '<div>bare text in div</div></body></html>')
    sec = convert_html_to_fb2_section(BeautifulSoup(html, 'html.parser'))
    assert '<p>\u2022 one <emphasis>it</emphasis></p>' in sec
    assert '<p>1. first</p>' in sec and '<p>2. second</p>' in sec
    assert '<cite>' in sec and '<p>bare text in div</p>' in sec
    doc = _FB2_HEADER + '<body>' + sec + '</body></FictionBook>'
    assert xc.validate_fb2(doc) == []


def test_unsupported_blocks_warn_with_aggregate_counter(caplog):
    html = ('<html><body><table><tr><td>cell text</td></tr></table>'
            '<table><tr><td>again</td></tr></table>'
            '<figure>pic</figure><p>kept</p></body></html>')
    with caplog.at_level('WARNING'):
        sec = convert_html_to_fb2_section(BeautifulSoup(html, 'html.parser'))
    assert '<p>kept</p>' in sec
    assert 'cell text' not in sec  # stage 1: tables are dropped, not inlined
    msgs = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    joined = ' '.join(msgs)
    assert 'Dropped 3 unsupported block(s)' in joined
    assert '<table> x2' in joined and '<figure> x1' in joined
