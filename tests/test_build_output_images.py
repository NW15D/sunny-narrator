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

    def _fake_ebook_convert(cmd, *args, **kwargs):
        seen['html_dir_files'] = os.listdir(os.path.dirname(cmd[1]))
        if len(cmd) >= 3:
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('OK')
        return MagicMock(returncode=0)

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('pypandoc.convert_text', return_value='<p>x</p>'), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_ebook_convert
        build_output("# Ch\n\ntext", "epub", {"title": "T"},
                     output_path=out, images_dir=str(images_dir))

    assert 'img1.png' in seen['html_dir_files']
