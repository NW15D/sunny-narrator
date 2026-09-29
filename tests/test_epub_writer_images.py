"""FB2 <binary> -> EPUB images: type sniffing, bad data, name clashes."""
import base64
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from epub_checks import check_epub
from src.epub_writer import _load_images, create_epub_from_fb2

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 16
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
GIF = b'GIF89a' + b'\x00' * 16
WEBP = b'RIFF\x10\x00\x00\x00WEBPVP8 ' + b'\x00' * 8
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
UNKNOWN = b'\x00\x01\x02\x03' * 4


def _binary(image_id, content_type, data, raw=None):
    payload = raw if raw is not None else base64.b64encode(data).decode()
    id_attr = f' id="{image_id}"' if image_id is not None else ''
    return f'<binary{id_attr} content-type="{content_type}">{payload}</binary>'


def test_type_comes_from_the_content_not_the_declaration():
    footer = ''.join([
        _binary('a', 'image/png', JPEG),       # mislabelled: really a JPEG
        _binary('b', 'image/jpeg', PNG),
        _binary('c', 'image/png', GIF),
        _binary('d', 'image/png', WEBP),
        _binary('e', 'image/png', SVG),
        _binary('f', 'image/jpg', UNKNOWN),    # non-standard label, unknown bytes -> jpeg
    ])
    images = _load_images(footer)
    assert {k: v['content_type'] for k, v in images.items()} == {
        'a': 'image/jpeg', 'b': 'image/png', 'c': 'image/gif',
        'd': 'image/webp', 'e': 'image/svg+xml', 'f': 'image/jpeg'}
    assert {k: v['file_name'] for k, v in images.items()} == {
        'a': 'images/a.jpg', 'b': 'images/b.png', 'c': 'images/c.gif',
        'd': 'images/d.webp', 'e': 'images/e.svg', 'f': 'images/f.jpg'}


def test_unusable_binaries_are_skipped():
    footer = ''.join([
        _binary('bad64', 'image/png', b'', raw='%%%not base64%%%'),
        _binary(None, 'image/png', PNG),
        _binary('tiff', 'image/tiff', UNKNOWN),
        _binary('ok', 'image/png', PNG),
    ])
    assert list(_load_images(footer)) == ['ok']


def test_whitespace_inside_base64_is_accepted():
    wrapped = '\n'.join(base64.b64encode(PNG).decode()[i:i + 8] for i in range(0, 32, 8))
    assert _load_images(_binary('w', 'image/png', b'', raw=wrapped))['w']['data'] == PNG


def test_clashing_file_names_are_made_unique():
    footer = _binary('a b.png', 'image/png', PNG) + _binary('a_b.png', 'image/png', PNG)
    names = [v['file_name'] for v in _load_images(footer).values()]
    assert len(set(names)) == 2


def test_epub_with_every_image_type_is_sound(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    ids = ['a', 'b', 'c', 'd', 'e']
    body = '<section><title><p>C</p></title>' + ''.join(f'<image l:href="#{i}"/>' for i in ids) + '</section>'
    footer = ''.join(_binary(i, 'image/png', d) for i, d in zip(ids, (JPEG, PNG, GIF, WEBP, SVG)))
    path = create_epub_from_fb2(header, body, footer, str(tmp_path / 'b'))
    assert check_epub(path) == []
    with zipfile.ZipFile(path) as zf:
        opf = zf.read('EPUB/content.opf').decode()
    for media in ('image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'):
        assert f'media-type="{media}"' in opf
