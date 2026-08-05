"""Tests for _ensure_balanced_tags stack-based XML balancing."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from xml_utils import _ensure_balanced_tags


def test_self_closing_not_counted():
    """Self-closing tags should not trigger extra closing tags."""
    xml = '<section><p>text</p><image/></section>'
    result = _ensure_balanced_tags(xml)
    assert result == xml, f"Expected no change, got: {result}"


def test_correct_closing_tag():
    """Unclosed tags should be closed with the correct tag name, not just </section>."""
    xml = '<section><p>unclosed'
    result = _ensure_balanced_tags(xml)
    assert result == '<section><p>unclosed</p></section>', f"Got: {result}"


def test_already_balanced():
    """Already balanced XML should remain unchanged."""
    xml = '<section><p>ok</p></section>'
    result = _ensure_balanced_tags(xml)
    assert result == xml, f"Expected no change, got: {result}"


def test_empty_line_void():
    """empty-line is a void element and should not be counted."""
    xml = '<section><empty-line/><p>t</p></section>'
    result = _ensure_balanced_tags(xml)
    assert result == xml, f"Expected no change, got: {result}"
