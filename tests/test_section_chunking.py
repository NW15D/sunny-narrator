"""C2: nested sections and <section id=...> must not lose content."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.xml_utils import prepare_chunks, prepare_chunks_with_sections


def _body(nested: bool, attrs: bool) -> str:
    open_tag = '<section id="ch1">' if attrs else '<section>'
    if nested:
        return (
            f'<body>{open_tag}<p>outer before</p>'
            '<section><p>inner text</p></section>'
            '<p>after inner</p></section></body>'
        )
    return f'<body>{open_tag}<p>only text</p></section></body>'


def test_nested_section_content_not_lost():
    chunks = prepare_chunks(_body(nested=True, attrs=False), 100000)
    joined = ''.join(chunks)
    assert 'outer before' in joined
    assert 'inner text' in joined
    assert 'after inner' in joined


def test_section_with_attributes_recognized():
    chunks = prepare_chunks_with_sections(_body(nested=False, attrs=True), 100000)
    joined = ''.join(''.join(section) for section in chunks)
    assert 'only text' in joined
    # Must not fall back to raw split of the whole body
    assert '<body>' not in joined
