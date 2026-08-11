"""
Tests for enhanced Calibre pipeline functionality.

Covers:
- ValidationReport / ValidationIssue dataclasses
- validate_epub() — EPUB structure validation
- validate_fb2() — FB2 structure validation
- validate_output() — format dispatch wrapper
"""

import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Path setup — ensure src/ is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock heavy third-party modules ONLY if they are missing. Both pypandoc and
# bs4 are real installed dependencies; mocking them unconditionally pollutes
# sys.modules for every later test module (B4 incident).
try:
    import pypandoc  # noqa: F401
except ImportError:
    sys.modules.setdefault('pypandoc', MagicMock())
try:
    import bs4  # noqa: F401
except ImportError:
    sys.modules.setdefault('bs4', MagicMock())

from src.calibre_pipeline import (
    ValidationIssue,
    ValidationReport,
    validate_epub,
    validate_fb2,
    validate_output,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal valid / invalid files on the fly
# ---------------------------------------------------------------------------

def _make_epub(tmp_dir: str, *, valid: bool = True, with_calibre_artifact: bool = False) -> str:
    """
    Create a minimal EPUB file (ZIP) for testing.

    Args:
        tmp_dir: Directory to create the file in.
        valid: If True, include all required EPUB components.
        with_calibre_artifact: If True, add a file with 'calibre' in the name.

    Returns:
        Path to the created EPUB file.
    """
    path = os.path.join(tmp_dir, "test.epub")
    with zipfile.ZipFile(path, 'w') as zf:
        if valid:
            # META-INF/container.xml
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?>\n'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                '  <rootfiles>\n'
                '    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>\n'
                '  </rootfiles>\n'
                '</container>',
            )
            # content.opf with required metadata
            zf.writestr(
                "content.opf",
                '<?xml version="1.0"?>\n'
                '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id">\n'
                '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                '    <dc:title>Test Book</dc:title>\n'
                '    <dc:creator>Test Author</dc:creator>\n'
                '    <dc:language>en</dc:language>\n'
                '  </metadata>\n'
                '</package>',
            )
            # TOC file
            zf.writestr("toc.xhtml", "<html><body>TOC</body></html>")
        else:
            # Invalid: just a random file, no container.xml, no OPF
            zf.writestr("random.txt", "not an epub")

        if with_calibre_artifact:
            zf.writestr("calibre_index.html", "<html></html>")

    return path


def _make_fb2(tmp_dir: str, *, valid: bool = True, with_calibre_artifact: bool = False) -> str:
    """
    Create a minimal FB2 file for testing.

    Args:
        tmp_dir: Directory to create the file in.
        valid: If True, include all required FB2 elements.
        with_calibre_artifact: If True, embed 'calibre-' string in content.

    Returns:
        Path to the created FB2 file.
    """
    path = os.path.join(tmp_dir, "test.fb2")

    if valid:
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
            '  <description>\n'
            '    <title-info>\n'
            '      <genre>fiction</genre>\n'
            '      <author><first-name>Test</first-name><last-name>Author</last-name></author>\n'
            '      <book-title>Test Book</book-title>\n'
            '      <lang>en</lang>\n'
            '    </title-info>\n'
            '  </description>\n'
            '  <body>\n'
            '    <section><p>Hello world</p></section>\n'
            '  </body>\n'
            '</FictionBook>\n'
        )
    else:
        # Invalid XML
        content = "<not-valid-xml><broken>"

    if with_calibre_artifact:
        content += "<!-- calibre-generated -->\n"

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    return path


def _make_docx(tmp_dir: str, *, valid: bool = True) -> str:
    """Create a minimal DOCX (OOXML ZIP) for testing."""
    path = os.path.join(tmp_dir, "test.docx")
    with zipfile.ZipFile(path, 'w') as zf:
        if valid:
            zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
            zf.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>')
        else:
            zf.writestr("random.txt", "not a docx")
    return path


def _make_pdf(tmp_dir: str, *, valid: bool = True) -> str:
    """Create a minimal PDF for testing."""
    path = os.path.join(tmp_dir, "test.pdf")
    if valid:
        with open(path, 'wb') as f:
            f.write(b"%PDF-1.4\n...content...\n%%EOF\n")
    else:
        with open(path, 'wb') as f:
            f.write(b"not a pdf at all")
    return path


# ===========================================================================
# TestValidation — dataclass unit tests
# ===========================================================================

class TestValidationReport:
    """Tests for ValidationReport and ValidationIssue dataclasses."""

    def test_default_report_is_invalid(self):
        """A fresh ValidationReport should default to is_valid=False."""
        report = ValidationReport()
        assert report.is_valid is False
        assert report.file_path == ""
        assert report.file_size == 0
        assert report.format == ""
        assert report.issues == []

    def test_add_issue(self):
        """add_issue() should append ValidationIssue to the list."""
        report = ValidationReport()
        report.add_issue("error", "Something broke", details="detail info", line=42)

        assert len(report.issues) == 1
        issue = report.issues[0]
        assert issue.severity == "error"
        assert issue.message == "Something broke"
        assert issue.details == "detail info"
        assert issue.file_line == 42

    def test_has_errors_true(self):
        """has_errors() returns True when at least one error-severity issue exists."""
        report = ValidationReport()
        report.add_issue("warning", "Minor issue")
        assert report.has_errors() is False

        report.add_issue("error", "Critical issue")
        assert report.has_errors() is True

    def test_has_errors_false_with_warnings_only(self):
        """has_errors() returns False when only warnings are present."""
        report = ValidationReport()
        report.add_issue("warning", "Just a warning")
        report.add_issue("warning", "Another warning")
        assert report.has_errors() is False

    def test_summary_pass(self):
        """summary() returns a human-readable PASS string."""
        report = ValidationReport(
            is_valid=True, file_path="/tmp/test.epub",
            file_size=1024, format="epub"
        )
        s = report.summary()
        assert "PASS" in s
        assert "test.epub" in s
        assert "1024" in s

    def test_summary_fail(self):
        """summary() returns a human-readable FAIL string."""
        report = ValidationReport(
            is_valid=False, file_path="/tmp/test.fb2",
            file_size=512, format="fb2"
        )
        report.add_issue("error", "Broken")
        s = report.summary()
        assert "FAIL" in s
        assert "1 error" in s

    def test_validation_issue_defaults(self):
        """ValidationIssue fields have sensible defaults."""
        issue = ValidationIssue(severity="warning", message="test")
        assert issue.details == ""
        assert issue.file_line == 0


# ===========================================================================
# TestValidation — EPUB validation
# ===========================================================================

class TestValidateEpub:
    """Tests for validate_epub()."""

    def test_valid_epub(self, tmp_path):
        """A well-formed EPUB should pass validation."""
        epub_path = _make_epub(str(tmp_path), valid=True)
        report = validate_epub(epub_path)

        assert report.is_valid is True
        assert report.format == "epub"
        assert report.file_size > 0
        assert not report.has_errors()

    def test_missing_file(self, tmp_path):
        """Non-existent file should produce an error."""
        report = validate_epub(str(tmp_path / "nonexistent.epub"))
        assert report.is_valid is False
        assert report.has_errors()
        assert any("does not exist" in i.message for i in report.issues)

    def test_empty_file(self, tmp_path):
        """Zero-byte file should produce an error."""
        empty = tmp_path / "empty.epub"
        empty.write_bytes(b"")
        report = validate_epub(str(empty))
        assert report.is_valid is False
        assert any("empty" in i.message.lower() for i in report.issues)

    def test_invalid_zip(self, tmp_path):
        """A file that is not a valid ZIP should produce an error."""
        bad = tmp_path / "bad.epub"
        bad.write_bytes(b"this is not a zip file at all")
        report = validate_epub(str(bad))
        assert report.is_valid is False
        assert any("ZIP" in i.message or "zip" in i.message.lower() for i in report.issues)

    def test_missing_container_xml(self, tmp_path):
        """EPUB without META-INF/container.xml should fail."""
        epub_path = str(tmp_path / "no_container.epub")
        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr("content.opf", "<package><metadata><dc:title>T</dc:title></metadata></package>")
        report = validate_epub(epub_path)
        assert report.is_valid is False
        assert any("container.xml" in i.message for i in report.issues)

    def test_missing_opf(self, tmp_path):
        """EPUB without an OPF file should fail."""
        epub_path = str(tmp_path / "no_opf.epub")
        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
        report = validate_epub(epub_path)
        assert report.is_valid is False
        assert any("OPF" in i.message for i in report.issues)

    def test_missing_dc_title(self, tmp_path):
        """OPF without <dc:title> should produce an error."""
        epub_path = str(tmp_path / "no_title.epub")
        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("content.opf", '<?xml version="1.0"?><package xmlns:dc="x"><metadata><dc:creator>A</dc:creator></metadata></package>')
        report = validate_epub(epub_path)
        assert report.is_valid is False
        assert any("dc:title" in i.message for i in report.issues)

    def test_no_toc_warning(self, tmp_path):
        """EPUB without TOC should produce a warning (not an error)."""
        epub_path = str(tmp_path / "no_toc.epub")
        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("content.opf", '<package><metadata><dc:title>T</dc:title><dc:creator>A</dc:creator></metadata></package>')
            # No TOC file at all
            zf.writestr("chapter1.xhtml", "<html><body>Chapter 1</body></html>")
        report = validate_epub(epub_path)
        # Should still be valid (TOC missing is a warning, not error)
        warnings = [i for i in report.issues if i.severity == "warning"]
        assert any("TOC" in i.message for i in warnings)

    def test_calibre_artifact_warning(self, tmp_path):
        """EPUB with calibre-named files should produce a warning."""
        epub_path = _make_epub(str(tmp_path), valid=True, with_calibre_artifact=True)
        report = validate_epub(epub_path)
        warnings = [i for i in report.issues if i.severity == "warning"]
        assert any("calibre" in i.message.lower() for i in warnings)
        # Still valid since calibre artifacts are warnings only
        assert report.is_valid is True


# ===========================================================================
# TestValidation — FB2 validation
# ===========================================================================

class TestValidateFb2:
    """Tests for validate_fb2()."""

    def test_valid_fb2(self, tmp_path):
        """A well-formed FB2 should pass validation."""
        fb2_path = _make_fb2(str(tmp_path), valid=True)
        report = validate_fb2(fb2_path)

        assert report.is_valid is True
        assert report.format == "fb2"
        assert report.file_size > 0
        assert not report.has_errors()

    def test_missing_file(self, tmp_path):
        """Non-existent file should produce an error."""
        report = validate_fb2(str(tmp_path / "nonexistent.fb2"))
        assert report.is_valid is False
        assert any("does not exist" in i.message for i in report.issues)

    def test_empty_file(self, tmp_path):
        """Zero-byte file should produce an error."""
        empty = tmp_path / "empty.fb2"
        empty.write_bytes(b"")
        report = validate_fb2(str(empty))
        assert report.is_valid is False
        assert any("empty" in i.message.lower() for i in report.issues)

    def test_invalid_xml(self, tmp_path):
        """Malformed XML should produce an error."""
        fb2_path = _make_fb2(str(tmp_path), valid=False)
        report = validate_fb2(fb2_path)
        assert report.is_valid is False
        assert any("XML" in i.message or "xml" in i.message.lower() for i in report.issues)

    def test_wrong_root_element(self, tmp_path):
        """XML with wrong root element should fail."""
        bad_root = tmp_path / "bad_root.fb2"
        bad_root.write_text(
            '<?xml version="1.0"?>\n<NotAFictionBook><body/></NotAFictionBook>',
            encoding='utf-8',
        )
        report = validate_fb2(str(bad_root))
        assert report.is_valid is False
        assert any("root element" in i.message.lower() for i in report.issues)

    def test_missing_title_info(self, tmp_path):
        """FB2 without <title-info> should fail."""
        no_title_info = tmp_path / "no_title_info.fb2"
        no_title_info.write_text(
            '<?xml version="1.0"?>\n'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
            '  <body><section><p>Text</p></section></body>\n'
            '</FictionBook>',
            encoding='utf-8',
        )
        report = validate_fb2(str(no_title_info))
        assert report.is_valid is False
        assert any("title-info" in i.message for i in report.issues)

    def test_missing_body(self, tmp_path):
        """FB2 without <body> should fail."""
        no_body = tmp_path / "no_body.fb2"
        no_body.write_text(
            '<?xml version="1.0"?>\n'
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">\n'
            '  <description><title-info><genre>fiction</genre></title-info></description>\n'
            '</FictionBook>',
            encoding='utf-8',
        )
        report = validate_fb2(str(no_body))
        assert report.is_valid is False
        assert any("body" in i.message.lower() for i in report.issues)

    def test_calibre_artifact_warning(self, tmp_path):
        """FB2 with calibre markers should produce a warning but still pass."""
        fb2_path = _make_fb2(str(tmp_path), valid=True, with_calibre_artifact=True)
        report = validate_fb2(fb2_path)
        warnings = [i for i in report.issues if i.severity == "warning"]
        assert any("calibre" in i.message.lower() for i in warnings)
        assert report.is_valid is True


# ===========================================================================
# TestValidation — validate_output() wrapper
# ===========================================================================

class TestValidateOutput:
    """Tests for validate_output() dispatch wrapper."""

    def test_dispatch_epub(self, tmp_path):
        """validate_output('epub') should call validate_epub."""
        epub_path = _make_epub(str(tmp_path), valid=True)
        report = validate_output(epub_path, "epub")
        assert report.format == "epub"
        assert report.is_valid is True

    def test_dispatch_docx(self, tmp_path):
        """validate_output('docx') should call validate_docx."""
        docx_path = _make_docx(str(tmp_path), valid=True)
        report = validate_output(docx_path, "docx")
        assert report.format == "docx"
        assert report.is_valid is True

    def test_dispatch_pdf(self, tmp_path):
        """validate_output('pdf') should call validate_pdf."""
        pdf_path = _make_pdf(str(tmp_path), valid=True)
        report = validate_output(pdf_path, "pdf")
        assert report.format == "pdf"
        assert report.is_valid is True

    def test_dispatch_fb2_rejected(self, tmp_path):
        """validate_output('fb2') must report error — FB2 belongs to classic pipeline."""
        fb2_path = _make_fb2(str(tmp_path), valid=True)
        report = validate_output(fb2_path, "fb2")
        assert report.format == "fb2"
        assert report.has_errors() is True
        assert "FB2" in " ".join(i.message for i in report.issues)

    def test_case_insensitive_format(self, tmp_path):
        """Format should be case-insensitive (EPUB, Epub, epub all work)."""
        epub_path = _make_epub(str(tmp_path), valid=True)
        for fmt in ("EPUB", "Epub", "epub"):
            report = validate_output(epub_path, fmt)
            assert report.is_valid is True

    def test_unsupported_format(self, tmp_path):
        """Unsupported format should produce an error."""
        dummy = tmp_path / "test.mobi"
        dummy.write_bytes(b"dummy")
        report = validate_output(str(dummy), "mobi")
        assert report.is_valid is False
        assert any("Unsupported" in i.message for i in report.issues)
