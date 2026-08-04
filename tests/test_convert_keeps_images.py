"""B4/C8: convert_to_markdown must persist extracted images."""
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from ebooklib import epub

from src.calibre_pipeline import convert_to_markdown, check_calibre_installed

PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
    'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def test_convert_to_markdown_keeps_images(tmp_path):
    if not check_calibre_installed():
        pytest.skip("calibre not installed")

    book = epub.EpubBook()
    book.set_identifier('sn-img-test')
    book.set_title('Image Book')
    book.set_language('en')
    img_item = epub.EpubItem(uid='img1', file_name='images/img1.png',
                             media_type='image/png', content=PNG_1X1)
    book.add_item(img_item)
    ch = epub.EpubHtml(title='Ch 1', file_name='chap1.xhtml', lang='en')
    ch.content = '<html><body><p>Text</p><img src="images/img1.png"/></body></html>'
    book.add_item(ch)
    book.toc = (ch,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav', ch]
    epub_path = str(tmp_path / 'imgbook.epub')
    epub.write_epub(epub_path, book)

    markdown_text, metadata = convert_to_markdown(epub_path)
    images_dir = os.path.splitext(epub_path)[0] + '_images'
    assert os.path.isdir(images_dir)
    assert any(f.lower().endswith('.png') for f in os.listdir(images_dir))
