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
    assert '<h1>T & T</h1>' in html
    assert 'by A' in html


def test_build_output_passes_metadata_to_calibre(tmp_path):
    from src.calibre_pipeline import build_output

    def _fake_ebook_convert(cmd, *args, **kwargs):
        if len(cmd) >= 3:
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('OK')
        return MagicMock(returncode=0)

    out = str(tmp_path / 'out.fb2')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('pypandoc.convert_text', return_value='<p>x</p>'), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_ebook_convert
        build_output("# Ch\n\ntext", "fb2",
                     {"title": "My Title", "author": "My Author", "language": "ru"},
                     output_path=out)
    cmd_args = mock_run.call_args[0][0]
    assert "--title" in cmd_args
    assert "My Title" in cmd_args
    assert "--authors" in cmd_args
    assert "My Author" in cmd_args
    assert "--language" in cmd_args
    assert "ru" in cmd_args
