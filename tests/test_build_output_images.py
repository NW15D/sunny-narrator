"""B5/C8: build_output must place book images next to the HTML given to Calibre."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_build_output_copies_images_next_to_html(tmp_path):
    from src.calibre_pipeline import build_output

    images_dir = tmp_path / 'book_images'
    images_dir.mkdir()
    (images_dir / 'img1.png').write_bytes(b'\x89PNG\r\n\x1a\nfakebytes')

    seen = {}

    # build_output's Markdown->HTML step shells out to pandoc via
    # subprocess.run too now (not pypandoc.convert_text — see
    # _markdown_to_html_file's docstring), so the fake side_effect must
    # branch on cmd[0] rather than assume every call is "ebook-convert cmd[1]
    # cmd[2]" (a pandoc call's cmd[2] is a flag like "-f", not a path).
    def _fake_run(cmd, *args, **kwargs):
        seen['html_dir_files'] = os.listdir(os.path.dirname(cmd[1]))
        if cmd[0] == "ebook-convert":
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('OK')
        else:
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('<p>x</p>')
        return MagicMock(returncode=0)

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run
        build_output("# Ch\n\ntext", "epub", {"title": "T"},
                     output_path=out, images_dir=str(images_dir))

    assert 'img1.png' in seen['html_dir_files']
