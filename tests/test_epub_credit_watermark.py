"""Always-on EPUB credit (issue #65): dc:contributor + one description line.

Canon (issue #65, note 775): no flags/env vars; the credit is reduced to the
GitHub link; it lives in the metadata (dc:contributor) and exactly once at the
end of the description. An FB2 annotation that already carries its own credit
paragraph (added by parse_xml since dc-004) must not yield a second copy, so a
re-run / a re-converted book keeps exactly one credit line.
"""
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from epub_checks import check_epub, fb2_file_to_epub
from src import fb2_handler, utils
from src.epub_writer import create_epub_from_fb2

GITHUB_URL = 'https://github.com/NW15D/sunny-narrator'
CREDIT = f'Sunny Narrator: {GITHUB_URL}'
CONTRIBUTOR = f'Sunny Narrator ({GITHUB_URL})'

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
BODY = '<section><title><p>Chapter 1</p></title><p>Hello world.</p></section>'

ANN_PLAIN = '<annotation><p>A test book.</p><p>Second line.</p></annotation>'
ANN_WITH_CREDIT = (f'<annotation><p>A test book.</p><p>Second line.</p>'
                   f'<p>{CREDIT}</p></annotation>')


def _header(annotation=''):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
            '<description><title-info><genre>prose</genre>'
            '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
            '<book-title>Credit Book</book-title><lang>en</lang>'
            f'{annotation}</title-info></description>')


def _opf(epub_path):
    with zipfile.ZipFile(epub_path) as zf:
        name = [n for n in zf.namelist() if n.endswith('.opf')][0]
        return zf.read(name).decode('utf-8')


def _description(opf):
    m = re.search(r'<dc:description[^>]*>(.*?)</dc:description>', opf, re.DOTALL)
    return m.group(1) if m else None


# --- single source of truth -------------------------------------------------

def test_credit_values_come_from_the_shared_module():
    assert utils.GITHUB_URL == GITHUB_URL
    assert utils.CREDIT_LINE == CREDIT


# --- dc:contributor (metadata watermark, always on) -------------------------

def test_contributor_is_always_present_even_without_an_annotation(tmp_path):
    opf = _opf(create_epub_from_fb2(_header(''), BODY, '', str(tmp_path / 'a')))
    assert opf.count('<dc:contributor') == 1
    assert f'<dc:contributor>{CONTRIBUTOR}</dc:contributor>' in opf


def test_contributor_appears_once_when_the_book_has_an_annotation(tmp_path):
    opf = _opf(create_epub_from_fb2(_header(ANN_PLAIN), BODY, '', str(tmp_path / 'a')))
    assert opf.count('<dc:contributor') == 1
    assert f'<dc:contributor>{CONTRIBUTOR}</dc:contributor>' in opf


# --- description credit line (once, at the end) -----------------------------

def test_credit_is_appended_to_the_end_of_the_description_once(tmp_path):
    opf = _opf(create_epub_from_fb2(_header(ANN_PLAIN), BODY, '', str(tmp_path / 'a')))
    description = _description(opf)
    assert description == f'A test book. Second line. {CREDIT}'
    assert description.count(GITHUB_URL) == 1


def test_no_duplicate_credit_when_the_annotation_already_carries_it(tmp_path):
    # dc-004 injects the credit into the FB2 annotation; it arrives with the
    # description and must not be appended a second time.
    opf = _opf(create_epub_from_fb2(_header(ANN_WITH_CREDIT), BODY, '', str(tmp_path / 'a')))
    description = _description(opf)
    assert description == f'A test book. Second line. {CREDIT}'
    assert description.count(GITHUB_URL) == 1


def test_double_conversion_keeps_exactly_one_credit(tmp_path):
    first = _opf(create_epub_from_fb2(_header(ANN_PLAIN), BODY, '', str(tmp_path / 'a')))
    second = _opf(create_epub_from_fb2(_header(ANN_PLAIN), BODY, '', str(tmp_path / 'b')))
    for opf in (first, second):
        assert _description(opf).count(GITHUB_URL) == 1
        assert opf.count('<dc:contributor') == 1


def test_fb2_pipeline_credit_reaches_the_epub_exactly_once(tmp_path):
    body, header, footer = fb2_handler.parse_xml(RICH)
    assert CREDIT in header                       # precondition: the FB2 credit is there
    epub_path = create_epub_from_fb2(header, body, footer, str(tmp_path / 'rich'))
    opf = _opf(epub_path)
    description = _description(opf)
    assert description.count(GITHUB_URL) == 1
    assert description.endswith(CREDIT)
    assert opf.count('<dc:contributor') == 1


def test_existing_metadata_survives_alongside_the_credit(tmp_path):
    epub_path = fb2_file_to_epub(RICH, str(tmp_path / 'rich'))
    opf = _opf(epub_path)
    assert '<dc:title>The Rich Book &amp; Its Parts</dc:title>' in opf
    assert opf.count('<dc:creator') == 2
    assert '<dc:subject>prose_classic</dc:subject>' in opf
    description = _description(opf)
    assert description.startswith('A test book. Second line.')
    assert description.endswith(CREDIT)
    assert description.count(GITHUB_URL) == 1
    assert check_epub(epub_path) == []


def test_no_description_no_forced_credit_line_but_contributor_stays(tmp_path):
    # Nothing is forced in: a book without an annotation keeps no description,
    # while the contributor (metadata watermark) is still present.
    opf = _opf(create_epub_from_fb2(_header(''), BODY, '', str(tmp_path / 'a')))
    assert _description(opf) is None
    assert f'<dc:contributor>{CONTRIBUTOR}</dc:contributor>' in opf
