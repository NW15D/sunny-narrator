"""Tests for src/epub_repair.py: EPUB validation and auto-repair logic."""
import os
import sys
import zipfile

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.epub_repair import (
    validate_epub,
    _find_opf_path,
    _validate_xml,
)

# NOTE: _validate_xml used to set `parser.recover = False` on the parser
# returned by get_safe_xml_parser(), but lxml's XMLParser has no settable
# `recover` attribute post-construction, so every OPF/XHTML validation used
# to yield a spurious AttributeError-based error regardless of the input's
# actual validity. Fixed by constructing a strict (recover=False) parser
# directly. RECOVER_BUG_MARKER/_structural_errors are kept as a defensive
# filter (a no-op now) in case the marker ever reappears.
RECOVER_BUG_MARKER = "no attribute 'recover'"


def _structural_errors(errors):
    """Filter out errors caused by the _validate_xml recover-attribute bug."""
    return [e for e in errors if RECOVER_BUG_MARKER not in e]

CONTAINER_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''

OPF = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test</dc:title>
    <dc:identifier id="uid">test-1</dc:identifier>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
  </spine>
</package>'''

XHTML = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Ch1</title></head>
<body><p>Hello world</p></body>
</html>'''


@pytest.fixture
def make_epub(tmp_path):
    """Factory: build an EPUB zip from a dict of {name: content}."""
    def _make(files, name='book.epub', store_mimetype=True):
        path = tmp_path / name
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname, content in files.items():
                data = content.encode('utf-8') if isinstance(content, str) else content
                if fname == 'mimetype' and store_mimetype:
                    zf.writestr(fname, data, compress_type=zipfile.ZIP_STORED)
                else:
                    zf.writestr(fname, data)
        return str(path)
    return _make


@pytest.fixture
def valid_epub(make_epub):
    return make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })


@pytest.fixture
def broken_epub(make_epub):
    """EPUB with compressed mimetype, missing container.xml, broken XHTML."""
    broken_xhtml = '<html><body><p>Unclosed paragraph'
    return make_epub({
        'mimetype': 'application/epub+zip',
        'content.opf': OPF,
        'chapter1.xhtml': broken_xhtml,
    }, store_mimetype=False)


# ---------------------------------------------------------------------------
# validate_epub
# ---------------------------------------------------------------------------

def test_validate_valid_epub_no_errors(valid_epub):
    assert validate_epub(valid_epub) == []


def test_validate_valid_epub_no_recover_bug_errors(valid_epub):
    """A valid EPUB produces no errors at all (recover-attribute bug fixed)."""
    errors = validate_epub(valid_epub)
    assert errors == []
    assert not any(RECOVER_BUG_MARKER in e for e in errors)


def test_validate_xml_valid_content_no_errors():
    """_validate_xml returns no errors for well-formed XML."""
    errors = _validate_xml(b'<root/>', 'test')
    assert errors == []


def test_validate_xml_reports_real_syntax_errors():
    """_validate_xml still reports genuine XML syntax errors."""
    errors = _validate_xml(b'<root><unclosed></root>', 'test')
    assert len(errors) == 1
    assert RECOVER_BUG_MARKER not in errors[0]


def test_validate_missing_file(tmp_path):
    errors = validate_epub(str(tmp_path / 'nonexistent.epub'))
    assert len(errors) == 1
    assert 'File not found' in errors[0]


def test_validate_not_a_zip(tmp_path):
    bad = tmp_path / 'bad.epub'
    bad.write_bytes(b'this is not a zip file at all')
    errors = validate_epub(str(bad))
    assert any('Invalid ZIP' in e for e in errors)


def test_validate_empty_zip(tmp_path):
    path = tmp_path / 'empty.epub'
    with zipfile.ZipFile(path, 'w'):
        pass
    errors = validate_epub(str(path))
    assert any('mimetype' in e for e in errors)
    assert any('container.xml' in e for e in errors)
    assert any('OPF' in e for e in errors)


def test_validate_compressed_mimetype(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    }, store_mimetype=False)
    errors = validate_epub(epub)
    assert any('uncompressed' in e for e in errors)


def test_validate_missing_container_xml(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    errors = validate_epub(epub)
    assert any('META-INF/container.xml' in e for e in errors)


def test_validate_broken_opf_xml(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': '<package><unclosed>',
        'OEBPS/chapter1.xhtml': XHTML,
    })
    errors = validate_epub(epub)
    assert any('OPF' in e for e in errors)


def test_validate_broken_xhtml_detected(make_epub):
    """Unescaped ampersand is not recoverable even in recover mode."""
    bad_xhtml = ('<?xml version="1.0"?>\n'
                 '<html xmlns="http://www.w3.org/1999/xhtml">'
                 '<body><p>AT&T</p></body></html>')
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': bad_xhtml,
    })
    errors = validate_epub(epub)
    assert any('XHTML' in e for e in errors)


def test_validate_missing_xhtml_file_not_an_error(make_epub):
    """XHTML listed in OPF but absent from zip: validator skips it silently."""
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        # chapter1.xhtml deliberately missing
    })
    # Missing XHTML files are skipped silently by the validator;
    # only the known recover-bug errors (from OPF parsing) may remain.
    assert _structural_errors(validate_epub(epub)) == []


# ---------------------------------------------------------------------------
# repair_epub
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _repair_xhtml internals
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _find_opf_path
# ---------------------------------------------------------------------------

def test_find_opf_from_container(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
    })
    with zipfile.ZipFile(epub) as zf:
        assert _find_opf_path(zf) == 'OEBPS/content.opf'


def test_find_opf_fallback_search(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'OEBPS/content.opf': OPF,
    })
    with zipfile.ZipFile(epub) as zf:
        assert _find_opf_path(zf) == 'OEBPS/content.opf'


def test_find_opf_none_when_absent(make_epub):
    epub = make_epub({'mimetype': 'application/epub+zip'})
    with zipfile.ZipFile(epub) as zf:
        assert _find_opf_path(zf) is None


# ---------------------------------------------------------------------------
# validate_and_repair_epub
# ---------------------------------------------------------------------------


