"""
The always-on credit of a translated book (issue #65): one wording
(src.utils: CREDIT_NAME, CREDIT_LINE, GITHUB_URL) in every format.

- FB2 / TXT (classic pipeline): our <translator> block with the repository as
  <home-page>, and the credit as the last annotation paragraph (a book
  without an annotation gets one). Added when the book is written, after the
  metadata translation (fb2_handler.add_credit from app.main): the LLM never
  sees it, so it is never translated or dropped.
- EPUB (epub_writer, Calibre's --comments): dc:contributor, and the credit as
  the description's own last paragraph, also with no annotation at all.
- Idempotent: the credit of an earlier run - in any wording, a translated
  "Солнечный рассказчик: <url>" too - is replaced, never repeated.
"""
import os
import re
import sys
import zipfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

import src.fb2_handler as fb2
import src.txt_handler as txt
import src.xmlcheck as xc
from src.epub_writer import create_epub_from_fb2
from src.utils import CREDIT_LINE, CREDIT_NAME, GITHUB_URL, credit_comment, is_credit_line

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
LEGACY = ('<translator><nickname>Sunny narrator opensource AI translator</nickname>'
          '<email>n@uwns.org</email></translator>')
OUR_BLOCK = f'<translator><nickname>{CREDIT_NAME}</nickname><home-page>{GITHUB_URL}</home-page></translator>'
BODY = '<section><title><p>Глава 1</p></title><p>Привет.</p></section>'


def _header(title_info_tail='', annotation=''):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
            '<description><title-info><genre>prose</genre>'
            '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
            f'<book-title>Credit Book</book-title>{annotation}<lang>ru</lang>{title_info_tail}'
            '</title-info></description>')


def _book(header):
    return f"{header}<body>{BODY}</body></FictionBook>"


def _credit_errors(book):
    """Schema errors about the credit (the test headers are minimal, so
    other errors - a genre, <document-info> - are not the subject)."""
    return [e for e in xc.validate_fb2(book) if 'annotation' in e or 'translator' in e]


def _annotation(header):
    return re.search(r'<annotation\b.*?</annotation>', header, flags=re.DOTALL).group(0)


# --- the wording -------------------------------------------------------------

def test_one_wording():
    assert CREDIT_LINE == f'{CREDIT_NAME}: {GITHUB_URL}'
    assert is_credit_line(CREDIT_LINE) and is_credit_line(f'Солнечный рассказчик: {GITHUB_URL}')
    long_text = f'This book was made with many tools, among them the one at {GITHUB_URL}. ' * 2
    assert not is_credit_line(long_text), "a sentence of the book that mentions the link is not a credit"


def test_credit_comment_puts_the_credit_last_and_once():
    assert credit_comment('') == CREDIT_LINE
    once = credit_comment('A test book.\nSecond line.')
    assert once == f'A test book.\nSecond line.\n\n{CREDIT_LINE}'
    assert credit_comment(once) == once
    translated = f'Книга.\n\nСолнечный рассказчик: {GITHUB_URL}'
    assert credit_comment(translated) == f'Книга.\n\n{CREDIT_LINE}'


# --- FB2 ---------------------------------------------------------------------

def test_the_source_header_carries_no_credit():
    """parse_xml feeds the metadata translation: the credit must not be in it."""
    _body, header, _footer = fb2.parse_xml(RICH)
    assert GITHUB_URL not in header and CREDIT_NAME not in header


def test_add_credit_writes_the_translator_and_the_annotation_line():
    _body, header, footer = fb2.parse_xml(RICH)
    credited = fb2.add_credit(header)
    assert OUR_BLOCK in credited
    assert credited.index('<translator>') < credited.index('<sequence')  # schema order
    assert _annotation(credited).endswith(f'<p>{CREDIT_LINE}</p></annotation>')
    assert credited.count(GITHUB_URL) == 2  # <home-page> and the annotation line
    assert fb2.add_credit(credited) == credited, "idempotent"


def test_a_book_without_annotation_gets_one():
    credited = fb2.add_credit(_header())
    assert f'</book-title><annotation><p>{CREDIT_LINE}</p></annotation><lang>' in credited
    assert _credit_errors(_book(credited)) == []


def test_the_legacy_block_is_rewritten_and_a_foreign_one_kept():
    other = '<translator><first-name>Jane</first-name><last-name>Doe</last-name></translator>'
    credited = fb2.add_credit(_header(title_info_tail=other + LEGACY))
    assert other in credited and OUR_BLOCK in credited
    assert 'n@uwns.org' not in credited and 'opensource AI translator' not in credited
    assert credited.count('<translator>') == 2


def test_a_translated_credit_of_an_earlier_run_is_replaced():
    annotation = f'<annotation><p>Книга о море.</p><p>Солнечный рассказчик: {GITHUB_URL}</p></annotation>'
    credited = fb2.add_credit(_header(annotation=annotation))
    assert _annotation(credited) == f'<annotation><p>Книга о море.</p><p>{CREDIT_LINE}</p></annotation>'


def test_a_txt_book_gets_the_credit_too(tmp_path):
    path = tmp_path / 'book.txt'
    path.write_text('Title\n\nFirst paragraph.\n\nSecond paragraph.\n', encoding='utf-8')
    body, header, footer = txt.parse_txt(str(path))
    credited = fb2.add_credit(header)
    assert OUR_BLOCK in credited and f'<p>{CREDIT_LINE}</p>' in credited
    assert _credit_errors(f"{credited}<body>{BODY}</body>{footer}") == []


# --- EPUB of the classic pipeline -------------------------------------------------------

def _opf(epub_path):
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(next(n for n in zf.namelist() if n.endswith('.opf'))).decode('utf-8')


def _description(opf):
    return re.search(r'<dc:description[^>]*>(.*?)</dc:description>', opf, re.DOTALL).group(1)


def test_epub_has_the_contributor_and_the_credit_paragraph(tmp_path):
    header = fb2.add_credit(_header(annotation='<annotation><p>A test book.</p><p>Second line.</p></annotation>'))
    opf = _opf(create_epub_from_fb2(header, BODY, '</FictionBook>', str(tmp_path / 'b')))
    assert opf.count(f'{CREDIT_NAME} ({GITHUB_URL})') == 1
    assert _description(opf) == f'A test book. Second line.\n\n{CREDIT_LINE}'


def test_epub_without_annotation_still_has_the_credit(tmp_path):
    opf = _opf(create_epub_from_fb2(_header(), BODY, '</FictionBook>', str(tmp_path / 'b')))
    assert _description(opf) == CREDIT_LINE


# --- Calibre pipeline -----------------------------------------------------------------

def _ebook_convert_cmd(tmp_path, metadata):
    from src.calibre_pipeline import build_output

    def fake_run(cmd, *args, **kwargs):
        out = cmd[2] if cmd[0] == "ebook-convert" else cmd[cmd.index('-o') + 1]
        with open(out, 'w', encoding='utf-8') as f:
            f.write('OK' if cmd[0] == "ebook-convert" else '<p>x</p>')
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
            patch('subprocess.run', side_effect=fake_run) as run:
        build_output("# Ch\n\ntext", "epub", metadata, output_path=str(tmp_path / 'out.epub'))
    [cmd] = [c.args[0] for c in run.call_args_list if c.args[0][0] == "ebook-convert"]
    return cmd


def test_calibre_passes_the_credit_as_producer_and_last_description_paragraph(tmp_path):
    cmd = _ebook_convert_cmd(tmp_path, {'title': 'T', 'author': 'A',
                                        'description': f'Книга.\nСолнечный рассказчик: {GITHUB_URL}'})
    assert cmd[cmd.index('--book-producer') + 1] == CREDIT_LINE
    assert cmd[cmd.index('--comments') + 1] == f'Книга.\n\n{CREDIT_LINE}'


def test_calibre_without_description_passes_the_credit_alone(tmp_path):
    cmd = _ebook_convert_cmd(tmp_path, {'title': 'T', 'author': 'A'})
    assert cmd[cmd.index('--comments') + 1] == CREDIT_LINE


def test_title_page_shows_the_credit_once():
    from src.calibre_pipeline import _generate_title_page
    html = _generate_title_page({'title': 'T', 'description': f'Книга.\n{CREDIT_LINE}'})
    assert html.count(GITHUB_URL) == 1 and f'<p><em>{CREDIT_LINE}</em></p>' in html
