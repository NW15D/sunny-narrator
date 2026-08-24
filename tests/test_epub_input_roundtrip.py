"""A2: parse_epub must read an EPUB without AttributeError."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ebooklib import epub

from src.epub_handler import parse_epub


def _make_minimal_epub(path):
    book = epub.EpubBook()
    book.set_identifier('sn-test-roundtrip-1')
    book.set_title('Test Book')
    book.set_language('en')
    book.add_author('Test Author')
    chapter = epub.EpubHtml(title='Chapter 1', file_name='chap1.xhtml', lang='en')
    chapter.content = '<html><body><h1>Chapter 1</h1><p>Hello sunny world.</p></body></html>'
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav', chapter]
    epub.write_epub(str(path), book)


def test_parse_epub_roundtrip(tmp_path):
    epub_path = tmp_path / "minimal.epub"
    _make_minimal_epub(epub_path)
    body, header, footer = parse_epub(str(epub_path))
    assert body
    assert 'Hello sunny world' in body
    assert header
    assert 'Test Book' in header
