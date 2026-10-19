"""F6 post-build: check_epub_toc() against synthetic EPUB zips (no Calibre)."""
import zipfile

from src.calibre_pipeline import check_epub_toc

NCX_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
    '<head><meta name="dtb:uid" content="test"/></head>'
    "<docTitle><text>Book</text></docTitle>"
    "<navMap>{navpoints}</navMap>"
    "</ncx>"
)

CONTENT_XHTML = (
    '<html xmlns="http://www.w3.org/1999/xhtml">'
    "<head><title>Chapter</title></head><body><h1>Chapter</h1></body></html>"
)


def _navpoint(i):
    return (
        f'<navPoint id="np{i}" playOrder="{i}">'
        f"<navLabel><text>Chapter {i}</text></navLabel>"
        f'<content src="content.xhtml#c{i}"/></navPoint>'
    )


def _write_epub(path, extra_files=None):
    files = {
        "mimetype": "application/epub+zip",
        "OEBPS/content.xhtml": CONTENT_XHTML,
    }
    files.update(extra_files or {})
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return str(path)


def test_single_navpoint_is_a_problem(tmp_path):
    ncx = NCX_TEMPLATE.format(navpoints=_navpoint(1))
    epub = _write_epub(tmp_path / "one_navpoint.epub", {"OEBPS/toc.ncx": ncx})
    problems = check_epub_toc(epub)
    assert problems, "a 1-navPoint TOC must be reported"
    assert any("navPoint" in p for p in problems)


def test_healthy_ncx_has_no_problems(tmp_path):
    navpoints = "".join(_navpoint(i) for i in (1, 2, 3))
    ncx = NCX_TEMPLATE.format(navpoints=navpoints)
    epub = _write_epub(tmp_path / "healthy.epub", {"OEBPS/toc.ncx": ncx})
    assert check_epub_toc(epub) == []


def test_unknown_title_is_a_problem(tmp_path):
    navpoints = "".join(_navpoint(i) for i in (1, 2, 3))
    broken = (
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        "<head><title>Unknown</title></head><body><p>x</p></body></html>"
    )
    epub = _write_epub(
        tmp_path / "unknown_title.epub",
        {
            "OEBPS/toc.ncx": NCX_TEMPLATE.format(navpoints=navpoints),
            "OEBPS/ch1.xhtml": broken,
        },
    )
    problems = check_epub_toc(epub)
    assert any("Unknown" in p for p in problems)


def test_missing_toc_is_a_problem(tmp_path):
    epub = _write_epub(tmp_path / "no_toc.epub")
    problems = check_epub_toc(epub)
    assert any("navigation" in p.lower() for p in problems)


def test_epub3_nav_document_with_links_accepted(tmp_path):
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        "<head><title>Book</title></head><body>"
        '<nav epub:type="toc"><ol>'
        '<li><a href="content.xhtml#c1">One</a></li>'
        '<li><a href="content.xhtml#c2">Two</a></li>'
        '<li><a href="content.xhtml#c3">Three</a></li>'
        "</ol></nav></body></html>"
    )
    epub = _write_epub(tmp_path / "nav_only.epub", {"OEBPS/nav.xhtml": nav})
    assert check_epub_toc(epub) == []
