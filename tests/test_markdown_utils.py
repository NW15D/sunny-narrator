"""Tests for markdown_utils module."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bs4 import BeautifulSoup
from src.markdown_utils import (
    split_markdown_by_size,
    clean_calibre_markers,
    extract_headings,
    copy_images_to_output,
)
from src.utils import validate_translation_length


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


def test_copy_images_to_output():
    """Test that images are properly copied to output."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test images
        images_dir = os.path.join(temp_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        open(os.path.join(images_dir, "test.png"), 'w').close()
        open(os.path.join(images_dir, "test.jpg"), 'w').close()
        
        with tempfile.TemporaryDirectory() as output_dir:
            copied = copy_images_to_output(temp_dir, output_dir)
            assert "test.png" in copied
            assert "test.jpg" in copied
            assert os.path.exists(os.path.join(output_dir, "test.png"))


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


def test_validate_translation_length_rejects_too_long():
    """Test length validation function from src.utils."""
    from src.utils import validate_translation_length
    
    # Test chunk with 50% diff (above threshold of 20%) - need >2000 chars for MIN_CHUNK_SIZE
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2000, "x" * 3000, "test"
    )
    # percent_diff = 50% > threshold 20%, so should_split = True
    assert percent_diff == 50.0
    assert should_split == True
    
    # Test chunk with 51% diff
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2000, "x" * 3020, "test"
    )
    assert percent_diff == 51.0
    assert should_split == True


def test_validate_translation_length_accepts_ok_and_rejects_small_chunk():
    """Test length validation function from src.utils."""
    # Test chunk with 50% diff (source_len >= 2000 required for split)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2500, "x" * 3750, "test"  # 50% diff, source >= MIN_CHUNK_SIZE
    )
    # percent_diff = 50% > threshold 20%, so should_split = True
    assert percent_diff == 50.0
    assert should_split == True
    assert is_valid == False

    # Test chunk with 15% diff (below threshold)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2500, "x" * 2875, "test"  # 15% diff
    )
    # percent_diff = 15% < threshold 20%, so should_split = False
    assert percent_diff == 15.0
    assert should_split == False
    assert is_valid == True

    # Test small chunk (source_len < MIN_CHUNK_SIZE = 2000) - should NOT split
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 1000, "x" * 1500, "test"  # 50% diff but source < MIN_CHUNK_SIZE
    )
    # should_split = False because source_len < MIN_CHUNK_SIZE
    assert percent_diff == 50.0
    assert should_split == False
    assert is_valid == True
