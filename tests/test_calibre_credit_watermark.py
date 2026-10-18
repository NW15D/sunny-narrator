"""Issue #65: Calibre pipeline credit watermark (--comments + shared builder).

Canon (issue #65): the credit is always on (no env/CLI flag to disable it),
its content is the GitHub link (optionally prefixed 'Sunny Narrator:'), no
email anywhere, and the single source of truth lives in src/utils.py - this
module must not re-declare the wording.

What is pinned here:
- ebook-convert receives `--comments` carrying the credit exactly once; the
  value is appended to the book's description (annotation slot for EPUB/DOCX,
  since ebook-convert has no --contributor) and is idempotent: a description
  that already contains the link (FB2 annotations now include the credit
  line, or a re-run over our own output) is passed through unchanged.
- `--book-producer` carries the shared credit line (no legacy email, no
  duplicated literal).
- The title page prints the same shared credit.

Convention (matches tests/test_calibre_metadata_args.py and friends): mock
only src.calibre_pipeline.check_calibre_installed and subprocess.run;
everything else (TempDir, file I/O, os.path.exists) runs for real.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils import CREDIT_LINE, GITHUB_URL

OLD_CREDIT_LITERAL = 'Sunny narrator opensource AI translator'


def _fake_run_factory():
    """Shared fake subprocess.run (same harness as test_calibre_metadata_args):
    pandoc calls write to the '-o <path>' file, ebook-convert calls write to
    cmd[2] (the output path)."""
    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('OK')
        else:
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
        return MagicMock(returncode=0)
    return _fake_run


def _ebook_convert_cmd(tmp_path, metadata):
    """Run build_output once against tmp_path and return the argv of the
    single ebook-convert call it makes."""
    from src.calibre_pipeline import build_output

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run_factory()
        build_output("# Ch\n\ntext", "epub", metadata, output_path=out)
    calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
    assert len(calls) == 1
    return calls[0]


def _flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# ---------------------------------------------------------------------------
# --comments: the credit lands in the output annotation exactly once
# ---------------------------------------------------------------------------

def test_comments_flag_is_passed_with_the_credit_line(tmp_path):
    """--comments must carry the credit with the GitHub link (already-existing
    descriptions get it appended; the title page alone is not enough)."""
    cmd = _ebook_convert_cmd(tmp_path, {"title": "T", "description": "A test book."})
    assert "--comments" in cmd
    comments = _flag_value(cmd, "--comments")
    assert comments.count(GITHUB_URL) == 1
    assert CREDIT_LINE in comments
    assert comments.endswith(CREDIT_LINE)
    assert "A test book." in comments


def test_comments_flag_is_passed_even_without_a_description(tmp_path):
    """No description -> the credit alone still fills the comments field;
    the watermark is always on."""
    cmd = _ebook_convert_cmd(tmp_path, {"title": "T"})
    assert "--comments" in cmd
    comments = _flag_value(cmd, "--comments")
    assert comments.count(GITHUB_URL) == 1
    assert CREDIT_LINE in comments


def test_comments_do_not_duplicate_when_description_already_has_the_link(tmp_path):
    """A description that already contains the GitHub link (FB2 annotation
    credit or re-conversion of our own output) must not gain a second copy."""
    desc = f"Why this book matters. {CREDIT_LINE}"
    cmd = _ebook_convert_cmd(tmp_path, {"title": "T", "description": desc})
    comments = _flag_value(cmd, "--comments")
    assert comments.count(GITHUB_URL) == 1
    assert "Why this book matters." in comments


def test_double_build_keeps_exactly_one_credit(tmp_path):
    """Running build_output twice on the same metadata yields identical
    --comments values with exactly one credit each time."""
    metadata = {"title": "T", "description": "A test book."}
    first = _flag_value(_ebook_convert_cmd(tmp_path, metadata), "--comments")
    second = _flag_value(_ebook_convert_cmd(tmp_path, metadata), "--comments")
    assert first == second
    assert second.count(GITHUB_URL) == 1


# ---------------------------------------------------------------------------
# --book-producer: shared credit line, no email, no duplicated literal
# ---------------------------------------------------------------------------

def test_book_producer_is_the_shared_credit_line(tmp_path):
    """--book-producer must carry the GitHub credit sourced from src.utils;
    no legacy email anywhere in the command."""
    cmd = _ebook_convert_cmd(tmp_path, {"title": "T"})
    assert "--book-producer" in cmd
    assert _flag_value(cmd, "--book-producer") == CREDIT_LINE
    joined = ' '.join(cmd)
    assert 'n@uwns.org' not in joined
    assert OLD_CREDIT_LITERAL not in joined


def test_translator_credit_constant_is_sourced_from_utils():
    """_TRANSLATOR_CREDIT stays importable (call sites/tests import it) but is
    no longer a duplicated literal: it is the shared src.utils line."""
    from src.calibre_pipeline import _TRANSLATOR_CREDIT
    assert _TRANSLATOR_CREDIT == CREDIT_LINE


# ---------------------------------------------------------------------------
# Title page + single source of truth
# ---------------------------------------------------------------------------

def test_title_page_prints_the_shared_credit():
    """The title page's credit <p> comes from the same source (no old
    literal left anywhere in the generated HTML)."""
    from src.calibre_pipeline import _generate_title_page
    html = _generate_title_page({"title": "T", "author": "A"})
    assert f"<p><em>{CREDIT_LINE}</em></p>" in html
    assert OLD_CREDIT_LITERAL not in html


def test_calibre_pipeline_hardcodes_neither_url_nor_old_literal():
    """Single source of truth: the credit URL must not appear as a string
    literal in the module, and the old credit sentence must be gone."""
    from src import calibre_pipeline
    source = Path(calibre_pipeline.__file__).read_text(encoding='utf-8')
    assert 'github.com/NW15D' not in source
    assert OLD_CREDIT_LITERAL not in source


# ---------------------------------------------------------------------------
# credit_comment() builder behaviour (direct, src/utils.py)
# ---------------------------------------------------------------------------

def test_credit_comment_builder_appends_once_and_is_idempotent():
    from src.utils import credit_comment
    assert credit_comment('') == CREDIT_LINE
    once = credit_comment('A test book.')
    assert once.startswith('A test book.')
    assert once.endswith(CREDIT_LINE)
    assert once.count(GITHUB_URL) == 1
    # re-application is a no-op (idempotency)
    assert credit_comment(once) == once
    # link present anywhere (not only appended) -> value returned unchanged
    mid = f'See {GITHUB_URL} for details.'
    assert credit_comment(mid) == mid
