"""Always-on credit (issue #65): FB2 home-page link + one annotation line.

Canon (issue #65, note 775): no flags/env vars, the credit content is reduced
to the GitHub link, the legacy n@uwns.org email is removed, and re-runs must
not duplicate anything (idempotency).
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.fb2_handler as fb2
import src.utils as utils
import src.xmlcheck as xc

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')

GITHUB_URL = 'https://github.com/NW15D/sunny-narrator'
CREDIT = f'Sunny Narrator: {GITHUB_URL}'
CREDIT_P = f'<p>{CREDIT}</p>'
LEGACY_TRANSLATOR = ('<translator><nickname>Sunny narrator opensource AI translator</nickname>'
                     '<email>n@uwns.org</email></translator>')
NO_ANNOTATION_BOOK = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
    '<description><title-info><author><nickname>a</nickname></author>'
    '<book-title>No Annotation</book-title><lang>en</lang></title-info></description>\n'
    '<body><section><p>text</p></section></body>\n'
    '</FictionBook>\n')


def _title_info(header):
    return re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL).group(0)


def _annotation(header):
    return re.search(r'<annotation\b.*?</annotation>', _title_info(header), flags=re.DOTALL).group(0)


# --- one source of truth ---------------------------------------------------

def test_credit_constants_and_builders_are_the_single_source_of_truth():
    assert utils.GITHUB_URL == GITHUB_URL
    assert utils.CREDIT_LINE == CREDIT
    assert utils.fb2_home_page() == GITHUB_URL
    assert utils.annotation_credit_text() == CREDIT


def test_translator_block_uses_the_url_and_drops_the_legacy_email():
    _body, header, _footer = fb2.parse_xml(RICH)
    translator = _title_info(header)
    assert f'<home-page>{GITHUB_URL}</home-page>' in translator
    assert 'n@uwns.org' not in header
    assert '<email>' not in translator
    assert translator.index('<nickname>') < translator.index('<home-page>')  # schema order
    assert translator.count('<home-page>') == 1


def test_fresh_translator_block_is_idempotent():
    _body, header, _footer = fb2.parse_xml(RICH)
    assert fb2.add_translator_info(header) == header


def test_legacy_translator_block_with_email_is_upgraded_in_place():
    legacy = ('<description><title-info><genre>prose_classic</genre>'
              '<book-title>T</book-title><lang>en</lang>'
              f'{LEGACY_TRANSLATOR}<sequence name="S" number="1"/></title-info></description>')
    upgraded = fb2.add_translator_info(legacy)
    assert 'n@uwns.org' not in upgraded
    assert f'<home-page>{GITHUB_URL}</home-page>' in upgraded
    assert upgraded.count('<home-page>') == 1
    assert upgraded.count('<translator>') == 1
    assert upgraded.count('<nickname>') == 1                     # upgraded, not duplicated
    assert upgraded.index('<translator>') < upgraded.index('<sequence')  # stays in place
    assert fb2.add_translator_info(upgraded) == upgraded          # idempotent


def test_legacy_translator_block_without_sequence_is_upgraded_in_place():
    legacy = ('<description><title-info><book-title>T</book-title><lang>en</lang>'
              f'{LEGACY_TRANSLATOR}</title-info></description>')
    upgraded = fb2.add_translator_info(legacy)
    assert 'n@uwns.org' not in upgraded
    assert f'<home-page>{GITHUB_URL}</home-page>' in upgraded
    assert fb2.add_translator_info(upgraded) == upgraded


def test_foreign_translator_is_left_alone():
    header = ('<description><title-info><book-title>T</book-title><lang>en</lang>'
              '<translator><nickname>Someone Else</nickname></translator></title-info></description>')
    upgraded = fb2.add_translator_info(header)
    assert '<nickname>Someone Else</nickname>' in upgraded
    assert 'Sunny narrator opensource AI translator' in upgraded
    assert f'<home-page>{GITHUB_URL}</home-page>' in upgraded


def test_header_without_title_info_is_untouched():
    header = '<description><document-info><id>x</id></document-info></description>'
    assert fb2.add_translator_info(header) == header
    assert fb2.add_annotation_credit(header) == header


# --- annotation credit line ------------------------------------------------

def test_annotation_credit_is_the_last_paragraph_and_appears_once():
    _body, header, _footer = fb2.parse_xml(RICH)
    ann = _annotation(header)
    assert header.count(CREDIT_P) == 1
    assert ann[:-len('</annotation>')].rstrip().endswith(CREDIT_P)  # last <p>
    # the paragraph is visible to the canonical metadata read
    meta = fb2.extract_metadata(header)
    assert meta['annotation'][-1] == CREDIT


def test_double_parse_xml_keeps_exactly_one_credit_paragraph():
    _b1, header1, _f1 = fb2.parse_xml(RICH)
    _b2, header2, _f2 = fb2.parse_xml(RICH)
    assert header1.count(CREDIT_P) == 1
    assert header2.count(CREDIT_P) == 1


def test_annotation_credit_editor_is_idempotent_on_produced_header():
    _body, header, _footer = fb2.parse_xml(RICH)
    assert fb2.add_annotation_credit(header) == header
    # and it stays single after the metadata update the pipeline performs
    meta = fb2.extract_metadata(header)
    meta['lang'] = 'ru'
    meta['book-title'] = 'Богатая книга'
    updated = fb2.update_header_with_metadata(header, meta)
    assert updated.count(CREDIT_P) == 1


def test_books_without_annotation_get_no_credit_line(tmp_path):
    book = tmp_path / 'no_annot.fb2'
    book.write_text(NO_ANNOTATION_BOOK, encoding='utf-8')
    _body, header, _footer = fb2.parse_xml(str(book))
    assert '<annotation' not in header                            # not forced in
    assert CREDIT not in header


def test_credit_keeps_schema_order_and_validates():
    _body, header, footer = fb2.parse_xml(RICH)
    meta = fb2.extract_metadata(header)
    meta['lang'] = 'ru'
    meta['book-title'] = 'Богатая книга'
    header = fb2.update_header_with_metadata(header, meta)
    assert header.index('<translator>') < header.index('<sequence')
    assert header.count(CREDIT_P) == 1
    book = f"{header}<body>\n<section><title><p>Гл</p></title><p>Привет</p></section></body>\n{footer}"
    assert xc.validate_fb2(book) == []
