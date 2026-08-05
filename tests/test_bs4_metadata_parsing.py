"""A1: bs4 calls in xml_utils must not raise TypeError."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.xml_utils import (
    extract_metadata,
    update_header_with_metadata,
    get_cover_image,
    replace_cover_image,
)

MINI_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
    ' xmlns:l="http://www.w3.org/1999/xlink">'
    '<description><title-info>'
    '<genre>prose</genre>'
    '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
    '<book-title>Test &amp; Title</book-title>'
    '<lang>en</lang>'
    '</title-info></description>'
    '</FictionBook>'
)


def test_extract_metadata_no_typeerror():
    md = extract_metadata(MINI_HEADER)
    assert md.get('book-title') == 'Test & Title'


def test_update_header_with_metadata_no_typeerror():
    out = update_header_with_metadata(MINI_HEADER, {'book-title': 'New Title'})
    assert isinstance(out, str)
    assert out


def test_get_cover_image_no_cover():
    href, data = get_cover_image(MINI_HEADER, '')
    assert href is None
    assert data is None


def test_replace_cover_image_adds_cover():
    header, footer, body = replace_cover_image(MINI_HEADER, '', '<body/>', 'QUJD')
    assert 'coverpage' in header
    assert 'cover.png' in footer
    assert body == '<body/>'
