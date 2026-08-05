"""B8: FB2 header must not nest <author> and must escape text values."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bs4 import BeautifulSoup

from src.epub_handler import build_fb2_header_from_metadata


def test_no_nested_authors_and_escaping():
    metadata = {
        'author': [
            {'first-name': 'John & Jane', 'last-name': 'Doe'},
            {'first-name': 'Alice', 'last-name': '<Smith>'},
        ],
        'book-title': 'Tom & Jerry',
        'genre': ['prose'],
        'lang': ['en'],
    }
    header = build_fb2_header_from_metadata(metadata)
    soup = BeautifulSoup(header, 'xml')
    authors = soup.find_all('author')
    assert len(authors) == 2
    for a in authors:
        assert a.find('author') is None
    title = soup.find('book-title')
    assert title.get_text() == 'Tom & Jerry'
