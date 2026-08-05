"""C3: chunk boundary must never land inside a tag."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.xml_utils import _find_chunk_boundary


def test_boundary_not_inside_tag():
    # '<' is within first 100 chars of the window, so the old code returns `end`
    # (60) which lands inside '<strong>'.
    text = 'A' * 50 + '<strong>' + 'B' * 100
    boundary = _find_chunk_boundary(text, 0, 60)
    assert boundary == 50  # start of the tag, not inside it


def test_boundary_after_full_tag_unchanged():
    # Normal case: a closing tag ends before `end` — boundary stays after it.
    text = '<p>' + 'x' * 50 + '</p>' + 'y' * 50
    boundary = _find_chunk_boundary(text, 0, 70)
    assert text[:boundary].endswith('</p>')
