"""Header edits must keep FB2 schema order and encoding sane."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.fb2_handler as fb2
import src.xmlcheck as xc

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')


def _translated_book():
    body, header, footer = fb2.parse_xml(RICH)
    meta = fb2.extract_metadata(header)
    meta['lang'] = 'ru'
    meta['book-title'] = 'Богатая книга'
    meta['author'] = [{'first-name': 'Джейн', 'last-name': 'Писатель', 'middle-name': 'К.'}]
    header = fb2.update_header_with_metadata(header, meta)
    return header, f"{header}<body>\n<section><title><p>Гл</p></title><p>Привет</p></section></body>\n{footer}"


def test_encoding_declaration_is_utf8_for_a_cp1251_source():
    _body, header, _footer = fb2.parse_xml(RICH)
    assert 'windows-1251' not in header and 'encoding="UTF-8"' in header


def test_translator_goes_before_sequence():
    _body, header, _footer = fb2.parse_xml(RICH)
    assert header.index('<translator>') < header.index('<sequence')
    assert fb2.add_translator_info(header) == header      # idempotent


def test_authors_stay_in_front_of_the_title_in_schema_order():
    header, book = _translated_book()
    assert header.index('<author>') < header.index('<book-title>')
    assert header.index('<first-name>Джейн') < header.index('<middle-name>') < header.index('<last-name>')
    assert xc.validate_fb2(book) == []


def test_language_is_updated_and_the_source_language_kept():
    header, _book = _translated_book()
    assert '<lang>ru</lang><src-lang>en</src-lang>' in header
    assert header.index('</lang>') < header.index('<translator>')


def test_new_cover_is_inserted_before_lang():
    header = ('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info>'
              '<genre>prose_classic</genre><author><last-name>A</last-name></author><book-title>T</book-title>'
              '<lang>en</lang></title-info></description>')
    new_header, _footer, _body = fb2.replace_cover_image(header, '</FictionBook>', '', 'aGVsbG8=')
    assert new_header.index('<coverpage>') < new_header.index('<lang>')


def test_cover_binary_is_found_whatever_the_attribute_order():
    header = ('<description><title-info><coverpage><image l:href="#c.jpg"/></coverpage>'
              '</title-info></description>')
    for footer in ('<binary id="c.jpg" content-type="image/jpeg">QUJD</binary>',
                   '<binary content-type="image/jpeg" id="c.jpg">QUJD</binary>',
                   "<binary id='c.jpg' content-type='image/jpeg'>QUJD</binary>"):
        assert fb2.get_cover_image(header, footer) == ('#c.jpg', 'QUJD'), footer


def test_replacing_the_cover_drops_the_old_binary_whatever_the_attribute_order():
    header = ('<description><title-info><coverpage><image l:href="#c.jpg"/></coverpage>'
              '</title-info></description>')
    footer = '<binary id="c.jpg" content-type="image/jpeg">OLD</binary></FictionBook>'
    _h, new_footer, _b = fb2.replace_cover_image(header, footer, '', 'NEW')
    assert 'OLD' not in new_footer and new_footer.count('<binary') == 1 and 'NEW' in new_footer


def test_new_cover_binary_gets_the_content_type_of_its_data():
    import base64
    header = ('<description><title-info><coverpage><image l:href="#c.jpg"/></coverpage>'
              '</title-info></description>')
    footer = '<binary id="c.jpg" content-type="image/jpeg">OLD</binary></FictionBook>'
    for data, expected in ((b'\xff\xd8\xff\xe0' + b'\x00' * 20, 'image/jpeg'),
                           (b'\x89PNG\r\n\x1a\n' + b'\x00' * 20, 'image/png'),
                           (b'GIF89a' + b'\x00' * 20, 'image/gif')):
        b64 = base64.b64encode(data).decode()
        _h, new_footer, _b = fb2.replace_cover_image(header, footer, '', b64)
        assert f'<binary content-type="{expected}" id="c.jpg">{b64}</binary>' in new_footer


def test_undecodable_cover_data_falls_back_to_png():
    from src.xml_utils import sniff_base64_image_type
    assert sniff_base64_image_type('%%%') == 'image/png'
    assert sniff_base64_image_type('') == 'image/png'
