"""Tests for F1: pandoc markdown→HTML must disable implicit_figures.

Pandoc's 'markdown' reader enables the implicit_figures extension: a
lone '![alt](img.jpg)' paragraph becomes
<figure><img ...><figcaption>alt</figcaption></figure>, which leaked
~181 visible 'Paragraph break image' caption lines into the book.
The md→html call in _markdown_to_html_file must use
'-f markdown-implicit_figures' to switch that extension off, so the
image stays an inline <img> inside a <p> without a figcaption.
"""
import re
import shutil

import pytest

from src import calibre_pipeline as cp


class _FakePandoc:
    """Minimal pypandoc stand-in: get_pandoc_path() only."""

    @staticmethod
    def get_pandoc_path():
        return 'pandoc'


# ---------------------------------------------------------------------------
# 1. unit: the '-f' format argument disables implicit_figures
# ---------------------------------------------------------------------------

def test_pandoc_markdown_to_html_disables_implicit_figures(tmp_path, monkeypatch):
    seen = []

    def fake_run_command(cmd, *args, **kwargs):
        seen.append(list(cmd))
        out_idx = cmd.index('-o')
        with open(cmd[out_idx + 1], 'w', encoding='utf-8') as f:
            f.write('<p>ok</p>')

    monkeypatch.setattr(cp, 'PANDOC_AVAILABLE', True)
    monkeypatch.setattr(cp, 'pypandoc', _FakePandoc)
    monkeypatch.setattr(cp, '_run_command', fake_run_command)

    cp._markdown_to_html_file(
        '# H\n\nHello world',
        str(tmp_path / 'out.html'),
        temp_dir=str(tmp_path),
        batch_chars=100000,
        timeout=60,
    )

    assert seen, 'no pandoc invocation was recorded'
    for cmd in seen:
        fmt_idx = cmd.index('-f')
        assert cmd[fmt_idx + 1] == 'markdown-implicit_figures', cmd
        # sanity: still Markdown→HTML, output file still requested
        assert '-t' in cmd and cmd[cmd.index('-t') + 1] == 'html'
        assert '-o' in cmd


# ---------------------------------------------------------------------------
# 2. integration: real pandoc on the exact 'Paragraph break image' input
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which('pandoc') is None, reason='pandoc binary not installed')
def test_single_image_no_figure_no_visible_caption(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, 'PANDOC_AVAILABLE', True)
    monkeypatch.setattr(cp, 'pypandoc', _FakePandoc)

    html_path = str(tmp_path / 'out.html')
    cp._markdown_to_html_file(
        '![Paragraph break image](x.jpg)\n\nBody text.',
        html_path,
        temp_dir=str(tmp_path),
        batch_chars=100000,
        timeout=120,
    )

    html = open(html_path, encoding='utf-8').read()
    assert '<img' in html, html
    assert 'figcaption' not in html, html
    assert 'alt="Paragraph break image"' in html, html
    # alt text must not leak as *visible* text (strip all tags first)
    visible = re.sub(r'<[^>]+>', '', html)
    assert 'Paragraph break image' not in visible, visible
    assert 'Body text.' in visible
