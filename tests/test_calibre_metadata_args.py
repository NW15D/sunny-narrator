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


def test_build_output_passes_metadata_to_calibre(tmp_path):
    from src.calibre_pipeline import build_output

    # build_output's Markdown->HTML step shells out to pandoc via
    # subprocess.run too now (not pypandoc.convert_text — see
    # _markdown_to_html_file's docstring), so the fake side_effect must
    # branch on cmd[0] rather than assume every call is "ebook-convert cmd[1]
    # cmd[2]" (a pandoc call's cmd[2] is a flag like "-f", not a path).
    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('OK')
        else:
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
        return MagicMock(returncode=0)

    out = str(tmp_path / 'out.docx')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run
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
