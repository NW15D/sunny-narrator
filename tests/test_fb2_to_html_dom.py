"""B10: _fb2_to_html must handle epigraph, tables and preserve attributes."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.epub_writer import _fb2_to_html


def test_epigraph_converted():
    out = _fb2_to_html('<epigraph><p>Quote</p></epigraph>')
    assert '<blockquote class="epigraph">' in out
    assert 'Quote' in out


def test_table_and_attributes_preserved():
    out = _fb2_to_html('<p id="p1">Text</p><table><tr><td>Cell</td></tr></table>')
    assert 'id="p1"' in out
    assert '<table>' in out
    assert '<td>Cell</td>' in out


def test_basic_mappings():
    fb2 = ('<title><p>Ch</p></title><p>A</p><empty-line/>'
           '<emphasis>B</emphasis><image l:href="#pic.png"/>')
    out = _fb2_to_html(fb2)
    assert '<h1>' in out
    assert '<em>B</em>' in out
    assert '<br' in out
    assert '<img src="images/pic.png"' in out
