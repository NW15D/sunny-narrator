"""C4: orphan closers at chunk start and cross-nesting must be fixed."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.xml_utils import _ensure_balanced_tags


def test_orphan_closer_at_start_gets_opener():
    result = _ensure_balanced_tags('</p>text<p>x</p>')
    assert result.startswith('<p>')
    assert result.count('<p>') == result.count('</p>')


def test_cross_nesting_explicitly_closed():
    assert _ensure_balanced_tags('<a><b></a>') == '<a><b></b></a>'


def test_unclosed_at_end_still_fixed():
    # Existing behaviour must be preserved.
    assert _ensure_balanced_tags('<p>text') == '<p>text</p>'
