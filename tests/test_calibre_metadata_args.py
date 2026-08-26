"""B3/C9: metadata must reach ebook-convert; title page must be a fragment."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_title_page_is_fragment():
    from src.calibre_pipeline import _generate_title_page
    html = _generate_title_page({'title': 'T & T', 'author': 'A'})
    assert '<html' not in html
    assert '<body' not in html
    # C2 fix: & is now escaped to &amp; for HTML safety
    assert '<h1>T &amp; T</h1>' in html
    assert 'by A' in html


def _fake_run_factory():
    """Shared fake subprocess.run: pandoc calls write to the -o path,
    ebook-convert calls write to cmd[2] — see other Calibre tests for why
    the branch is needed (pandoc's cmd[2] is a flag, not a path)."""
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


def test_build_output_passes_metadata_to_calibre(tmp_path):
    from src.calibre_pipeline import build_output

    out = str(tmp_path / 'out.docx')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run_factory()
        build_output("# Ch\n\ntext", "docx",
                     {"title": "My Title", "author": "My Author", "language": "ru"},
                     output_path=out)
    ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
    assert len(ebook_calls) == 1
    cmd_args = ebook_calls[0]
    assert "--title" in cmd_args
    assert "My Title" in cmd_args
    assert "--authors" in cmd_args
    assert "My Author" in cmd_args
    assert "--language" in cmd_args
    assert "ru" in cmd_args


def test_build_output_language_flag_uses_target_not_source(tmp_path):
    """--language must reflect the translation's target language, not the
    source book's OPF <dc:language> that ends up in metadata['language'].

    Regression test: build_output used to pass metadata['language'] (read
    straight from the source EPUB's OPF by extract_metadata_from_opf)
    straight through to --language, so a book translated en->ru shipped
    with an EPUB whose own metadata still claimed "en".
    """
    from src.calibre_pipeline import build_output

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run_factory()
        build_output("# Ch\n\ntext", "epub",
                     {"title": "T", "language": "en"},  # source language
                     output_path=out, target_lang="german")  # translation target
    ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
    cmd_args = ebook_calls[0]
    lang_idx = cmd_args.index("--language")
    assert cmd_args[lang_idx + 1] == "de", (
        f"--language must be the target language code ('de'), not the "
        f"source metadata's 'en': got {cmd_args[lang_idx + 1]!r}"
    )
    assert "en" not in cmd_args


def test_build_output_credits_translator(tmp_path):
    """Output metadata must credit the AI translator (--book-producer),
    matching the <translator> tag the classic FB2 pipeline already writes
    via fb2_handler.add_translator_info()."""
    from src.calibre_pipeline import build_output, _TRANSLATOR_CREDIT

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run_factory()
        build_output("# Ch\n\ntext", "epub", {"title": "T"}, output_path=out)
    ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
    cmd_args = ebook_calls[0]
    assert "--book-producer" in cmd_args
    assert _TRANSLATOR_CREDIT in cmd_args
