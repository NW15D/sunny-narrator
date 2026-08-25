"""
Tests for the build_output()/_markdown_to_html_file() rewrite.

Background: on a real ~920KB book, build_output's Markdown->HTML step
(pypandoc.convert_text() called once on the whole book, held as one Python
string, with no timeout) stalled/OOM'd with no traceback — the log simply
stopped after pypandoc's own "Running pandoc..." debug line. Because
batched.sh ran books sequentially with `wait $app_pid`, that silent hang
blocked every remaining book in the batch too, and the finished translation
(2.4M+ LLM tokens) was never written anywhere and got thrown away.

These tests cover the fix (batched, file-to-file pandoc conversion via
_markdown_to_html_file with a real enforced timeout, plus a markdown-direct-
to-Calibre fallback) and close coverage gaps that existed in build_output
before the rewrite (empty markdown, auto-filename generation, Calibre error
paths, temp-dir cleanup) — see the "build_output() coverage gaps" section of
the investigation this fix came out of.

Convention (matches tests/test_calibre_metadata_args.py and friends):
mock only src.calibre_pipeline.check_calibre_installed and subprocess.run;
everything else (TempDir, file I/O, os.path.exists) runs for real against
real files in tmp_path.
"""
import os
import sys
import subprocess as sp
import tempfile as _tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _fake_run_writes_files(cmd, *args, **kwargs):
    """Default subprocess.run side_effect: writes real output for both the
    pandoc batch call(s) ("-o <path>") and the final ebook-convert call
    (argv[2]), so downstream real os.path.exists()/open() calls see genuine
    files."""
    if cmd[0] == "ebook-convert":
        with open(cmd[2], 'w', encoding='utf-8') as f:
            f.write('OUTPUT')
    else:
        out_path = cmd[cmd.index('-o') + 1]
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('<p>x</p>')
    return MagicMock(returncode=0)


# ---------------------------------------------------------------------------
# 1. pandoc is invoked file-to-file, with a real timeout
# ---------------------------------------------------------------------------

def test_pandoc_invoked_file_to_file_with_timeout(tmp_path):
    """The whole point of the fix: pandoc must run as a subprocess against
    files on disk (with an enforced timeout), never pypandoc.convert_text()
    with the book's full text passed in memory."""
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")
    seen = []

    def _fake_run(cmd, *args, timeout=None, **kwargs):
        seen.append((cmd, timeout))
        return _fake_run_writes_files(cmd, *args, timeout=timeout, **kwargs)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        build_output("# Ch\n\nHello world", "epub", metadata, output_path=out_path)

    pandoc_calls = [(c, t) for c, t in seen if c[0] != "ebook-convert"]
    assert len(pandoc_calls) == 1
    cmd, timeout = pandoc_calls[0]
    assert '-o' in cmd
    assert '-f' in cmd and 'markdown' in cmd
    assert '-t' in cmd and 'html' in cmd
    # The book text itself never appears as a bare command-line argument —
    # it's written to a file first (that file's *path* is one of the args).
    assert all(len(arg) < 200 for arg in cmd)
    assert timeout is not None and timeout > 0


# ---------------------------------------------------------------------------
# 2. large markdown is split into multiple pandoc batches
# ---------------------------------------------------------------------------

def test_markdown_to_html_file_batches_large_input(tmp_path):
    from src.calibre_pipeline import _markdown_to_html_file

    markdown = "\n\n".join(
        f"## Section {i}\n\nSome text here that repeats a bit to add length."
        for i in range(50)
    )
    assert len(markdown) > 1000

    calls = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        out = cmd[cmd.index('-o') + 1]
        with open(out, 'w', encoding='utf-8') as f:
            f.write(f"<p>batch {len(calls)}</p>")
        return MagicMock(returncode=0)

    html_path = str(tmp_path / "output.html")
    with patch('subprocess.run', side_effect=_fake_run):
        _markdown_to_html_file(markdown, html_path, temp_dir=str(tmp_path),
                               batch_chars=200, timeout=30)

    assert len(calls) >= 2, "large input should be split into multiple pandoc batches"

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    for i in range(1, len(calls) + 1):
        assert f"batch {i}" in html, "html_path must accumulate every batch, in order"


# ---------------------------------------------------------------------------
# 3. a stuck/timed-out pandoc call fails loudly, not silently
# ---------------------------------------------------------------------------

def test_markdown_to_html_file_timeout_raises_value_error(tmp_path):
    """Regression test for the incident: the old pypandoc.convert_text()
    call had no timeout and could hang forever with the process producing no
    further log output. _markdown_to_html_file must instead raise promptly
    with a message that says what happened."""
    from src.calibre_pipeline import _markdown_to_html_file

    def _fake_run(cmd, *args, **kwargs):
        raise sp.TimeoutExpired(cmd, kwargs.get('timeout', 1))

    html_path = str(tmp_path / "output.html")
    with patch('subprocess.run', side_effect=_fake_run):
        with pytest.raises(ValueError, match=r"(?i)timed? ?out"):
            _markdown_to_html_file("# Ch\n\ntext", html_path, temp_dir=str(tmp_path),
                                   batch_chars=200000, timeout=5)


# ---------------------------------------------------------------------------
# 4. pandoc missing / failing falls back to feeding Calibre markdown directly
# ---------------------------------------------------------------------------

def test_build_output_falls_back_to_markdown_when_pandoc_fails(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")
    ebook_cmds = []
    seen = {}

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            ebook_cmds.append(cmd)
            # TempDir is rmtree'd once build_output returns, so read the
            # fallback file's content here, while it still exists.
            with open(cmd[1], 'r', encoding='utf-8') as f:
                seen['content'] = f.read()
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('EPUB')
            return MagicMock(returncode=0)
        raise sp.TimeoutExpired(cmd, kwargs.get('timeout', 1))

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        result = build_output("# Ch\n\nHello world", "epub", metadata, output_path=out_path)

    assert result == out_path
    assert len(ebook_cmds) == 1
    fed_path = ebook_cmds[0][1]
    assert fed_path.endswith('.md'), "Calibre should be fed the raw markdown, not an HTML file"
    assert 'Hello world' in seen['content']


def test_build_output_falls_back_when_pandoc_not_installed(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")

    def _fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "ebook-convert", "pandoc must never be invoked when PANDOC_AVAILABLE is False"
        with open(cmd[2], 'w', encoding='utf-8') as f:
            f.write('EPUB')
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('src.calibre_pipeline.PANDOC_AVAILABLE', False), \
         patch('subprocess.run', side_effect=_fake_run):
        result = build_output("# Ch\n\nHello world", "epub", metadata, output_path=out_path)

    assert result == out_path


# ---------------------------------------------------------------------------
# 5. missing ebook-convert output -> ValueError (previously zero coverage)
# ---------------------------------------------------------------------------

def test_build_output_raises_when_output_file_missing(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] != "ebook-convert":
            out = cmd[cmd.index('-o') + 1]
            with open(out, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
        # ebook-convert "succeeds" but writes nothing.
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        with pytest.raises(ValueError, match="not created"):
            build_output("# Ch\n\ntext", "epub", metadata, output_path=out_path)


# ---------------------------------------------------------------------------
# 6. Calibre CalledProcessError -> ValueError with (truncated) stderr
# ---------------------------------------------------------------------------

def test_build_output_calibre_error_includes_stderr(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] != "ebook-convert":
            out = cmd[cmd.index('-o') + 1]
            with open(out, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
            return MagicMock(returncode=0)
        err = sp.CalledProcessError(1, cmd)
        err.stderr = "boom: disk full"
        raise err

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        with pytest.raises(ValueError, match="boom: disk full"):
            build_output("# Ch\n\ntext", "epub", metadata, output_path=out_path)


def test_build_output_calibre_error_unknown_when_no_stderr(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] != "ebook-convert":
            out = cmd[cmd.index('-o') + 1]
            with open(out, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
            return MagicMock(returncode=0)
        err = sp.CalledProcessError(1, cmd)
        err.stderr = None
        raise err

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        with pytest.raises(ValueError, match="Unknown error"):
            build_output("# Ch\n\ntext", "epub", metadata, output_path=out_path)


# ---------------------------------------------------------------------------
# 7. output.html on disk holds POST-mutation content
# ---------------------------------------------------------------------------

def test_build_output_html_on_disk_is_post_mutation(tmp_path):
    """The file handed to ebook-convert must be pandoc's output AFTER
    Calibre-marker cleanup and image-src rewriting — tests/
    test_build_output_images.py only ever checked which files were copied
    into the temp dir, never what ended up inside output.html itself."""
    from src.calibre_pipeline import build_output

    images_dir = tmp_path / "images_src"
    images_dir.mkdir()
    (images_dir / "pic.png").write_bytes(b"\x89PNG fake")

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")
    seen_html = {}

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            with open(cmd[1], 'r', encoding='utf-8') as f:
                seen_html['content'] = f.read()
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('EPUB')
        else:
            out = cmd[cmd.index('-o') + 1]
            with open(out, 'w', encoding='utf-8') as f:
                # Pandoc-shaped output containing a Calibre comment marker
                # and an <img> using the "images/" prefix HTMLZ conversion
                # produces.
                f.write('<!-- 3 --><p>Text</p><img src="images/pic.png">')
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        build_output("# Ch\n\ntext", "epub", metadata, output_path=out_path,
                     images_dir=str(images_dir))

    html = seen_html['content']
    assert '<!--' not in html, "Calibre marker must be cleaned before ebook-convert sees the file"
    assert 'src="pic.png"' in html
    assert 'images/pic.png' not in html


# ---------------------------------------------------------------------------
# 8. empty/whitespace markdown
# ---------------------------------------------------------------------------

def test_build_output_rejects_empty_markdown():
    from src.calibre_pipeline import build_output

    with pytest.raises(ValueError, match="empty"):
        build_output("   \n\n  ", "epub", {"title": "T"})


# ---------------------------------------------------------------------------
# 9. auto-generated output filename
# ---------------------------------------------------------------------------

def test_build_output_auto_filename(tmp_path):
    from src.calibre_pipeline import build_output

    input_path = str(tmp_path / "SourceBook.epub")
    long_title = "A Very: Special/Book?? Title " + "x" * 60
    metadata = {"title": long_title, "author": "A", "language": "en"}

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run_writes_files):
        result = build_output("# Ch\n\ntext", "epub", metadata,
                              input_path=input_path, target_lang="russian")

    # Saved next to the source file (not CWD), with a language marker.
    assert os.path.dirname(result) == str(tmp_path)
    basename = os.path.basename(result)
    assert basename.endswith("_ru.epub")
    safe_title_part = basename[: -len("_ru.epub")]
    assert len(safe_title_part) <= 50
    assert all(c.isalnum() or c in ('_', '-') for c in safe_title_part)


# ---------------------------------------------------------------------------
# 10. temp dir is cleaned up on the failure path too
# ---------------------------------------------------------------------------

def test_build_output_cleans_temp_dir_on_failure(tmp_path):
    from src.calibre_pipeline import build_output

    metadata = {"title": "T", "author": "A", "language": "en"}
    out_path = str(tmp_path / "out.epub")
    created = []
    orig_mkdtemp = _tempfile.mkdtemp

    def _tracking_mkdtemp(*a, **kw):
        d = orig_mkdtemp(*a, **kw)
        created.append(d)
        return d

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] != "ebook-convert":
            out = cmd[cmd.index('-o') + 1]
            with open(out, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
            return MagicMock(returncode=0)
        raise FileNotFoundError("ebook-convert vanished")

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('tempfile.mkdtemp', side_effect=_tracking_mkdtemp), \
         patch('subprocess.run', side_effect=_fake_run):
        with pytest.raises(FileNotFoundError):
            build_output("# Ch\n\ntext", "epub", metadata, output_path=out_path)

    assert created, "TempDir should have created a directory before failing"
    assert not os.path.exists(created[-1]), "temp dir must be cleaned up even when build_output raises"
