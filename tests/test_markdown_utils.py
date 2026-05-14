"""Tests for markdown_utils module."""
import pytest
from src.markdown_utils import (
    split_markdown_by_size,
    generate_toc_html,
    clean_calibre_markers,
)


def test_split_markdown_by_size_small_text():
    """Test that small text returns as single chunk."""
    text = "Hello world\n\nThis is a test."
    chunks = split_markdown_by_size(text, target_size=1000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_markdown_by_size_large_text():
    """Test that large text is split into multiple chunks."""
    text = "# Chapter 1\n\n" + "word " * 1000 + "\n# Chapter 2\n\n" + "word " * 1000
    chunks = split_markdown_by_size(text, target_size=2000)
    assert len(chunks) >= 2


def test_clean_calibre_markers():
    """Test that Calibre markers are removed from text."""
    text = "Hello <!-- 1 -->world{#calibre_link-1 .calibre1}</p>"
    cleaned = clean_calibre_markers(text)
    assert "1" not in cleaned
