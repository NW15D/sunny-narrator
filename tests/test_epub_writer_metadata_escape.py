"""B2/C3: metadata must not be double-escaped in EPUB output."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.epub_writer import create_epub_from_fb2

HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
    '<description><title-info>'
    '<genre>prose</genre>'
    '<author><first-name>John &amp; Jane</first-name><last-name>Doe</last-name></author>'
    '<book-title>Tom &amp; Jerry Stories</book-title>'
    '<lang>en</lang>'
    '</title-info></description>'
)
BODY = '<section><title><p>Chapter 1</p></title><p>Hello world.</p></section>'


def test_metadata_not_double_escaped(tmp_path):
    out_base = str(tmp_path / "book")
    epub_path = create_epub_from_fb2(HEADER, BODY, '', out_base)
    assert os.path.exists(epub_path)
    with zipfile.ZipFile(epub_path) as zf:
        opf_name = [n for n in zf.namelist() if n.endswith('.opf')][0]
        opf = zf.read(opf_name).decode('utf-8')
    assert '&amp;amp;' not in opf
    assert 'Tom &amp; Jerry Stories' in opf
