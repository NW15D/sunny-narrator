"""B10: FB2 -> XHTML conversion must handle epigraph, tables and preserve attributes."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

sys.path.insert(0, os.path.dirname(__file__))
from epub_checks import fragment_to_html


def test_epigraph_converted():
    out = fragment_to_html('<epigraph><p>Quote</p></epigraph>')
    assert '<blockquote class="epigraph">' in out
    assert 'Quote' in out


def test_table_and_attributes_preserved():
    out = fragment_to_html('<p id="p1">Text</p><table><tr><td>Cell</td></tr></table>')
    assert 'id="p1"' in out
    assert '<table>' in out
    assert '<td>Cell</td>' in out


def test_basic_mappings():
    fb2 = ('<title><p>Ch</p></title><p>A</p><empty-line/>'
           '<emphasis>B</emphasis><image l:href="#pic.png"/>')
    out = fragment_to_html(fb2, images={'pic.png': {'file_name': 'images/pic.png'}})
    assert '<h1>' in out
    assert '<em>B</em>' in out
    assert '<br' in out
    assert '<img src="images/pic.png"' in out
