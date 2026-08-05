"""B11: FB2 -> EPUB roundtrip: structure, mimetype, metadata, images."""
import os
import sys
import zipfile
import xml.dom.minidom

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.epub_writer import fb2_to_epub

FB2 = '''<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description>
<title-info>
<genre>prose</genre>
<author><first-name>Test</first-name><last-name>Author</last-name></author>
<book-title>Round &amp; Trip</book-title>
<lang>en</lang>
</title-info>
</description>
<body>
<section><title><p>Chapter One</p></title><p>Hello <emphasis>world</emphasis>.</p></section>
</body>
<binary content-type="image/png" id="cover.png">aGVsbG8=</binary>
</FictionBook>'''


def test_fb2_epub_roundtrip(tmp_path):
    fb2_path = tmp_path / 'book.fb2'
    fb2_path.write_text(FB2, encoding='utf-8')
    epub_path = fb2_to_epub(str(fb2_path), str(tmp_path / 'book'))
    assert os.path.exists(epub_path)

    with zipfile.ZipFile(epub_path) as zf:
        names = zf.namelist()
        # mimetype must be first and stored uncompressed
        assert names[0] == 'mimetype'
        info = zf.getinfo('mimetype')
        assert info.compress_type == zipfile.ZIP_STORED
        assert zf.read('mimetype') == b'application/epub+zip'
        assert 'META-INF/container.xml' in names
        opf_name = [n for n in names if n.endswith('.opf')][0]
        opf = zf.read(opf_name).decode('utf-8')
        assert '&amp;amp;' not in opf
        assert 'Round &amp; Trip' in opf
        # all XML/XHTML documents must be well-formed
        for n in names:
            if n.endswith(('.xhtml', '.xml')):
                xml.dom.minidom.parseString(zf.read(n))
        # image from <binary> must be present
        assert any('cover' in n for n in names)
