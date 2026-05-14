"""Tests for markdown_utils module."""
import pytest
from bs4 import BeautifulSoup
from src.markdown_utils import (
    split_markdown_by_size,
    generate_toc_html,
    clean_calibre_markers,
    extract_headings,
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


def test_extract_headings_from_html():
    """Test extracting headings from HTML using BeautifulSoup."""
    html_content = '<h1>Chapter 1</h1><h2>Section 1.1</h2><h2>Section 1.2</h2>'
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = extract_headings(soup)
    
    assert len(headings) == 3
    assert headings[0]['level'] == 1
    assert headings[0]['text'] == 'Chapter 1'
    assert headings[1]['level'] == 2
    assert headings[1]['text'] == 'Section 1.1'
    assert headings[2]['level'] == 2
    assert headings[2]['text'] == 'Section 1.2'


def test_add_toc_to_html():
    """Test adding TOC to HTML content."""
    from src.markdown_utils import generate_toc_html
    
    toc_data = [
        {'level': 1, 'text': 'Chapter 1', 'id': 'chapter-1'},
        {'level': 2, 'text': 'Section 1.1', 'id': 'section-1-1'},
        {'level': 2, 'text': 'Section 1.2', 'id': 'section-1-2'},
        {'level': 1, 'text': 'Chapter 2', 'id': 'chapter-2'},
    ]
    
    toc_html = generate_toc_html(toc_data)
    assert '<nav class="toc">' in toc_html
    assert 'Chapter 1' in toc_html
    assert 'Section 1.1' in toc_html
