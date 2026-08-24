"""Tests for src/epub_repair.py: EPUB validation and auto-repair logic."""
import os
import sys
import zipfile

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.epub_repair import (
    validate_epub,
    repair_epub,
    validate_and_repair_epub,
    _find_opf_path,
    _repair_xhtml,
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

def test_repair_adds_missing_mimetype(make_epub, tmp_path):
    epub = make_epub({
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    out = str(tmp_path / 'repaired.epub')
    out_path, repairs = repair_epub(epub, out)
    assert out_path == out
    assert any('Added missing mimetype' in r for r in repairs)
    with zipfile.ZipFile(out) as zf:
        assert zf.read('mimetype') == b'application/epub+zip'
        assert zf.namelist()[0] == 'mimetype'
        assert zf.getinfo('mimetype').compress_type == zipfile.ZIP_STORED


def test_repair_fixes_compressed_mimetype(make_epub, tmp_path):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    }, store_mimetype=False)
    out = str(tmp_path / 'repaired.epub')
    _, repairs = repair_epub(epub, out)
    assert any('mimetype' in r for r in repairs)
    with zipfile.ZipFile(out) as zf:
        assert zf.getinfo('mimetype').compress_type == zipfile.ZIP_STORED


def test_repair_adds_missing_container_xml(make_epub, tmp_path):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    out = str(tmp_path / 'repaired.epub')
    _, repairs = repair_epub(epub, out)
    assert any('container.xml' in r for r in repairs)
    with zipfile.ZipFile(out) as zf:
        container = zf.read('META-INF/container.xml').decode('utf-8')
        assert 'OEBPS/content.opf' in container  # found existing OPF candidate


def test_repair_broken_xhtml_closes_tags(make_epub, tmp_path):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': '<html><body><p>Unclosed paragraph',
    })
    out = str(tmp_path / 'repaired.epub')
    _, repairs = repair_epub(epub, out)
    assert any('Fixed unclosed tags' in r for r in repairs)
    with zipfile.ZipFile(out) as zf:
        fixed = zf.read('OEBPS/chapter1.xhtml').decode('utf-8')
    assert '</p>' in fixed
    assert '</body>' in fixed
    assert 'xmlns=' in fixed  # namespace was added
    assert fixed.startswith('<?xml')  # declaration added


def test_repair_preserves_valid_xhtml(make_epub, tmp_path):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    out = str(tmp_path / 'repaired.epub')
    repair_epub(epub, out)
    with zipfile.ZipFile(out) as zf:
        assert zf.read('OEBPS/chapter1.xhtml').decode('utf-8') == XHTML


def test_repair_empty_xhtml_content(make_epub, tmp_path):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': '',
    })
    out = str(tmp_path / 'repaired.epub')
    out_path, repairs = repair_epub(epub, out)
    assert os.path.exists(out_path)
    with zipfile.ZipFile(out) as zf:
        content = zf.read('OEBPS/chapter1.xhtml').decode('utf-8')
    assert content.startswith('<?xml')  # declaration added to empty file


def test_repair_overwrite_creates_backup(make_epub):
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    original_bytes = open(epub, 'rb').read()
    out_path, repairs = repair_epub(epub)  # no output_path -> overwrite
    assert out_path == epub
    assert os.path.exists(epub + '.backup')
    assert open(epub + '.backup', 'rb').read() == original_bytes
    assert repairs  # at least header + mimetype rewrite


def test_repair_does_not_touch_original_when_output_given(valid_epub, tmp_path):
    original_bytes = open(valid_epub, 'rb').read()
    out = str(tmp_path / 'copy.epub')
    repair_epub(valid_epub, out)
    assert open(valid_epub, 'rb').read() == original_bytes
    assert not os.path.exists(valid_epub + '.backup')


def test_repair_invalid_zip_raises(tmp_path):
    bad = tmp_path / 'bad.epub'
    bad.write_bytes(b'not a zip')
    with pytest.raises(Exception) as exc_info:
        repair_epub(str(bad), str(tmp_path / 'out.epub'))
    assert 'repair failed' in str(exc_info.value)
    assert not os.path.exists(str(bad) + '.repair.tmp')  # temp cleaned up


# ---------------------------------------------------------------------------
# _repair_xhtml internals
# ---------------------------------------------------------------------------

def test_repair_xhtml_void_tags_in_xml_context():
    """In XML mode lxml treats <br> as an opening tag and nests following
    content inside it — pinned actual behavior (HTML-style void tags are
    NOT converted to self-closing siblings)."""
    html = '<html xmlns="http://www.w3.org/1999/xhtml"><body>a<br>b<hr></body></html>'
    result, repairs = _repair_xhtml(html.encode('utf-8'), 'test.xhtml')
    text = result.decode('utf-8')
    assert '<br>b<hr/></br>' in text
    assert any('Fixed unclosed tags' in r for r in repairs)


def test_repair_xhtml_self_closing_regex_path():
    """When lxml cannot build a tree (bare fragment), the regex repair
    converts void tags with attributes to self-closing form."""
    result, _ = _repair_xhtml(b'hello <br clear="all"> world', 'test.xhtml')
    text = result.decode('utf-8')
    assert '<br clear="all" />' in text


def test_repair_xhtml_already_self_closed_not_doubled():
    html = '<html xmlns="http://www.w3.org/1999/xhtml"><body><br/></body></html>'
    result, _ = _repair_xhtml(html.encode('utf-8'), 'test.xhtml')
    text = result.decode('utf-8')
    assert '/ />' not in text


def test_repair_xhtml_empty_bytes():
    result, repairs = _repair_xhtml(b'', 'empty.xhtml')
    text = result.decode('utf-8')
    assert text.startswith('<?xml')
    assert any('XML declaration' in r for r in repairs)


def test_repair_xhtml_namespace_added():
    html = '<html><body><p>x</p></body></html>'
    result, repairs = _repair_xhtml(html.encode('utf-8'), 'test.xhtml')
    text = result.decode('utf-8')
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in text
    assert any('namespace' in r for r in repairs)


def test_repair_xhtml_namespace_not_doubled():
    result, repairs = _repair_xhtml(XHTML.encode('utf-8'), 'test.xhtml')
    text = result.decode('utf-8')
    assert text.count('xmlns="http://www.w3.org/1999/xhtml"') == 1
    assert not any('namespace' in r for r in repairs)


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

def test_validate_and_repair_valid_epub_ideal(valid_epub):
    path, repairs, errors = validate_and_repair_epub(valid_epub)
    assert errors == []
    assert repairs == ['EPUB is valid']


def test_validate_and_repair_valid_epub_actual(valid_epub):
    """A valid EPUB round-trips through validate_and_repair_epub cleanly:
    no repairs needed, no errors, and container.xml is untouched."""
    path, repairs, errors = validate_and_repair_epub(valid_epub)
    assert path == valid_epub
    assert repairs == ['EPUB is valid']
    assert errors == []
    with zipfile.ZipFile(valid_epub) as zf:
        assert 'META-INF/container.xml' in zf.namelist()


def test_validate_and_repair_fixes_broken(broken_epub, tmp_path):
    out = str(tmp_path / 'repaired.epub')
    path, repairs, errors = validate_and_repair_epub(broken_epub, out)
    assert path == out
    assert repairs
    assert errors == []
    with zipfile.ZipFile(out) as zf:
        assert zf.getinfo('mimetype').compress_type == zipfile.ZIP_STORED
        assert 'META-INF/container.xml' in zf.namelist()
        fixed = zf.read('chapter1.xhtml').decode('utf-8')
    assert '</p>' in fixed


def test_repair_preserves_existing_container(make_epub, tmp_path):
    """An EXISTING container.xml must survive repair_epub unchanged (it used
    to be silently dropped: the copy loop skipped it assuming it was
    "already handled", but it was only actually (re)written when missing)."""
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': CONTAINER_XML,
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    out = str(tmp_path / 'repaired.epub')
    repair_epub(epub, out)
    with zipfile.ZipFile(out) as zf:
        assert 'META-INF/container.xml' in zf.namelist()
        assert zf.read('META-INF/container.xml').decode('utf-8') == CONTAINER_XML


def test_validate_and_repair_missing_container_end_to_end(make_epub, tmp_path):
    """Missing container.xml is regenerated end-to-end."""
    epub = make_epub({
        'mimetype': 'application/epub+zip',
        'OEBPS/content.opf': OPF,
        'OEBPS/chapter1.xhtml': XHTML,
    })
    out = str(tmp_path / 'repaired.epub')
    _, repairs, errors = validate_and_repair_epub(epub, out)
    assert _structural_errors(errors) == []
    with zipfile.ZipFile(out) as zf:
        container = zf.read('META-INF/container.xml').decode('utf-8')
    assert 'OEBPS/content.opf' in container


def test_validate_and_repair_unrepairable(tmp_path):
    """Garbage file cannot be repaired; error surfaces, no infinite loop."""
    bad = tmp_path / 'garbage.epub'
    bad.write_bytes(b'garbage data, not a zip')
    # repair_epub raises; validate_and_repair_epub does not catch it.
    with pytest.raises(Exception, match='repair failed'):
        validate_and_repair_epub(str(bad))
