"""
Tests for Calibre pipeline format scope (TDD: RED phase).

Per product decision:
- Calibre pipeline is for DOCX/EPUB/PDF only (structure-preserving formats
  that Calibre round-trips well).
- FB2 stays with the classic pipeline 1 (direct XML manipulation), because
  Calibre's HTMLZ intermediate loses poem/stanza/v structure and flattens it
  into <p>/<empty-line/> (verified empirically).
"""
import sys
import os
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# convert_to_markdown: input format scope
# ---------------------------------------------------------------------------

def _fake_pandoc_run(cmd, *args, **kwargs):
    """Shared subprocess.run side_effect for tests that mock zipfile.ZipFile
    (so the ebook-convert HTMLZ output doesn't need to be a real file) but
    still need the pandoc HTML->Markdown call (now a real subprocess.run
    invocation — see _markdown_to_html_file's docstring in
    src/calibre_pipeline.py) to actually produce its "-o" output file, since
    the code reads that file back for real (only zipfile.ZipFile is mocked,
    not builtins.open)."""
    if cmd[0] != "ebook-convert" and '-o' in cmd:
        out_path = cmd[cmd.index('-o') + 1]
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("markdown")
    return MagicMock(returncode=0)


def test_convert_to_markdown_accepts_docx():
    """convert_to_markdown must accept .docx input."""
    from src.calibre_pipeline import convert_to_markdown

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('src.calibre_pipeline.TempDir') as mock_td, \
         patch('zipfile.ZipFile') as mock_zf, \
         patch('subprocess.run') as mock_run, \
         patch('src.calibre_pipeline.extract_metadata_from_opf', return_value={}), \
         patch('os.path.exists', return_value=True):
        mock_run.side_effect = _fake_pandoc_run
        # TempDir context manager pointing at a REAL temp dir
        import tempfile as _tf
        _real = _tf.mkdtemp(prefix="calibre_conv_")
        mock_td.return_value.__enter__.return_value = _real
        # ZipFile context manager with index.html and metadata.opf
        mock_zip = MagicMock()
        mock_zip.namelist.return_value = ['index.html']
        mock_zip.read.return_value = b"<html><body>docx content</body></html>"
        mock_zf.return_value.__enter__.return_value = mock_zip

        md, meta = convert_to_markdown("book.docx")
        assert md == "markdown"


def test_convert_to_markdown_accepts_pdf():
    """convert_to_markdown must accept .pdf input."""
    from src.calibre_pipeline import convert_to_markdown

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('src.calibre_pipeline.TempDir') as mock_td, \
         patch('zipfile.ZipFile') as mock_zf, \
         patch('subprocess.run') as mock_run, \
         patch('src.calibre_pipeline.extract_metadata_from_opf', return_value={}), \
         patch('os.path.exists', return_value=True):
        mock_run.side_effect = _fake_pandoc_run
        import tempfile as _tf
        _real = _tf.mkdtemp(prefix="calibre_conv_")
        mock_td.return_value.__enter__.return_value = _real
        mock_zip = MagicMock()
        mock_zip.namelist.return_value = ['index.html']
        mock_zip.read.return_value = b"<html><body>pdf content</body></html>"
        mock_zf.return_value.__enter__.return_value = mock_zip

        md, meta = convert_to_markdown("book.pdf")
        assert md == "markdown"


def test_convert_to_markdown_rejects_fb2():
    """convert_to_markdown must REJECT .fb2 — FB2 belongs to classic pipeline."""
    from src.calibre_pipeline import convert_to_markdown

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            convert_to_markdown("book.fb2")
            assert False, "Expected ValueError for FB2 input in Calibre pipeline"
        except ValueError as e:
            assert 'fb2' in str(e).lower() or 'unsupported' in str(e).lower()


def test_convert_to_markdown_rejects_fbz():
    """convert_to_markdown must REJECT .fbz (FB2 archive) too."""
    from src.calibre_pipeline import convert_to_markdown

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            convert_to_markdown("book.fbz")
            assert False, "Expected ValueError for FBZ input in Calibre pipeline"
        except ValueError as e:
            assert 'unsupported' in str(e).lower()


# ---------------------------------------------------------------------------
# build_output: output format scope
# ---------------------------------------------------------------------------

def _fake_build_output_run(cmd, *args, **kwargs):
    """subprocess.run side_effect for build_output tests: writes real output
    for both the pandoc Markdown->HTML batch call(s) and the final
    ebook-convert call, so real os.path.exists()/open() checks downstream
    see genuine files instead of relying on a global os.path.exists mock."""
    if cmd[0] == "ebook-convert":
        with open(cmd[2], 'w', encoding='utf-8') as f:
            f.write('OK')
    else:
        out_path = cmd[cmd.index('-o') + 1]
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("<html><body>Test</body></html>")
    return MagicMock(returncode=0)


def test_build_output_accepts_docx(tmp_path):
    """build_output must support .docx output."""
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.docx")

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_build_output_run
        out = build_output("# Ch\n\nText", "docx", metadata, output_path=out_path)
        assert out == out_path
        ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
        assert len(ebook_calls) == 1
        assert out_path in ebook_calls[0]


def test_build_output_accepts_pdf(tmp_path):
    """build_output must support .pdf output."""
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.pdf")

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_build_output_run
        out = build_output("# Ch\n\nText", "pdf", metadata, output_path=out_path)
        assert out == out_path
        ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
        assert len(ebook_calls) == 1
        assert out_path in ebook_calls[0]


def test_build_output_rejects_fb2(tmp_path):
    """build_output must REJECT fb2 — FB2 output belongs to classic pipeline."""
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True):
        try:
            build_output("# Ch\n\nText", "fb2", metadata, output_path=str(tmp_path / "out.fb2"))
            assert False, "Expected ValueError for FB2 output in Calibre pipeline"
        except ValueError as e:
            assert 'unsupported' in str(e).lower() or 'fb2' in str(e).lower()


# ---------------------------------------------------------------------------
# run_pipeline: format validation
# ---------------------------------------------------------------------------

def test_run_pipeline_rejects_fb2_input():
    """run_pipeline must reject FB2 input with clear error."""
    from src.calibre_pipeline import run_pipeline

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            run_pipeline("book.fb2", output_format="epub", skip_validation=True)
            assert False, "Expected ValueError for FB2 input in run_pipeline"
        except (ValueError, SystemExit) as e:
            msg = str(e).lower()
            assert 'fb2' in msg, f"Error should mention FB2: {e}"
            assert 'unsupported' in msg, f"Error should say unsupported: {e}"
            assert 'classic' in msg, f"Error should point to classic pipeline: {e}"


def test_run_pipeline_rejects_fb2_output():
    """run_pipeline must reject fb2 output format."""
    from src.calibre_pipeline import run_pipeline

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            run_pipeline("book.epub", output_format="fb2", skip_validation=True)
            assert False, "Expected ValueError for FB2 output in run_pipeline"
        except (ValueError, SystemExit) as e:
            msg = str(e).lower()
            assert 'fb2' in msg, f"Error should mention FB2: {e}"
            assert 'unsupported' in msg, f"Error should say unsupported: {e}"
            assert 'classic' in msg, f"Error should point to classic pipeline: {e}"

# ---------------------------------------------------------------------------
# validate_output dispatch: docx/pdf supported, fb2 rejected
# ---------------------------------------------------------------------------

def test_validate_output_docx(tmp_path):
    """validate_output must dispatch to docx validation."""
    from src.calibre_pipeline import validate_output
    import zipfile
    p = tmp_path / "out.docx"
    with zipfile.ZipFile(str(p), 'w') as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", '<?xml version="1.0"?><w:document/>')
    report = validate_output(str(p), "docx")
    assert report.format == "docx"
    assert report.is_valid is True


def test_validate_output_pdf(tmp_path):
    """validate_output must dispatch to pdf validation."""
    from src.calibre_pipeline import validate_output
    p = tmp_path / "out.pdf"
    p.write_bytes(b"%PDF-1.4\ncontent\n%%EOF\n")
    report = validate_output(str(p), "pdf")
    assert report.format == "pdf"
    assert report.is_valid is True


def test_validate_output_fb2_rejected(tmp_path):
    """validate_output must NOT accept fb2 (classic pipeline owns FB2)."""
    from src.calibre_pipeline import validate_output
    p = tmp_path / "out.fb2"
    p.write_text('<?xml version="1.0"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><book-title>T</book-title></title-info></description><body><p>hi</p></body></FictionBook>')
    report = validate_output(str(p), "fb2")
    assert report.has_errors() is True
