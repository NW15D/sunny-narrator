"""
Tests for FB2 chunking with XML tag balancing
"""
import sys
import os
from unittest.mock import MagicMock

# Mock third party modules
sys.modules['bs4'] = MagicMock()
sys.modules['bs4.BeautifulSoup'] = MagicMock()

# Add project root to sys.path
sys.path.insert(0, "/home/neo/.openclaw/workspace-dev/sunny-narrator")

import src.fb2_handler as fb2
from src.config import Config

# Mock config
fb2.config = Config()
fb2.config.debug = False


def test_find_chunk_boundary():
    """Test that chunk boundary finder respects closing tags"""
    print("\n--- Test: Find Chunk Boundary ---")
    
    text = "<p>Paragraph 1</p><p>Paragraph 2</p><p>Paragraph 3</p>"
    start = 0
    preferred_end = 30  # Somewhere in the middle
    
    boundary = fb2._find_chunk_boundary(text, start, preferred_end)
    print(f"Text: {text}")
    print(f"Preferred end: {preferred_end}, Actual boundary: {boundary}")
    print(f"Chunk: '{text[start:boundary]}'")
    
    # Should end at a tag boundary (either opening or closing)
    chunk = text[start:boundary]
    # Check that we don't have unclosed tags
    open_p = chunk.count("<p>")
    close_p = chunk.count("</p>")
    # It's OK if we have one more opening tag (it will be closed by _ensure_balanced_tags)
    assert open_p >= close_p, f"Should not have more closing than opening tags: open={open_p}, close={close_p}"
    assert boundary > start, "Boundary should be after start"
    print("PASS")


def test_ensure_balanced_tags():
    """Test that unclosed tags are properly closed"""
    print("\n--- Test: Ensure Balanced Tags ---")
    
    # Chunk with unclosed <p> and <strong>
    chunk = "<p>This is <strong>bold text"
    result = fb2._ensure_balanced_tags(chunk)
    print(f"Input:  '{chunk}'")
    print(f"Output: '{result}'")
    
    assert result == "<p>This is <strong>bold text</strong></p>", \
        f"Expected closing tags added, got: {result}"
    print("PASS")


def test_ensure_balanced_tags_already_balanced():
    """Test that already balanced tags are not modified"""
    print("\n--- Test: Already Balanced Tags ---")
    
    chunk = "<p>This is <strong>bold</strong> text</p>"
    result = fb2._ensure_balanced_tags(chunk)
    print(f"Input:  '{chunk}'")
    print(f"Output: '{result}'")
    
    assert result == chunk, f"Should remain unchanged, got: {result}"
    print("PASS")


def test_prepare_chunks_basic():
    """Test basic chunking of a section"""
    print("\n--- Test: Prepare Chunks Basic ---")
    
    # Create a body with one section containing multiple paragraphs
    body = """<section>
<p>First paragraph with some text.</p>
<p>Second paragraph with more text.</p>
<p>Third paragraph with even more text content here.</p>
</section>"""
    
    # Use small max_len to force splitting
    max_len = 80
    sections = fb2.prepare_chunks(body, max_len)
    
    print(f"Number of sections: {len(sections)}")
    print(f"Chunks in section 0: {len(sections[0]) if sections else 0}")
    
    for i, chunk in enumerate(sections[0] if sections else []):
        print(f"  Chunk {i}: {chunk[:50]}... (len={len(chunk)})")
        # Each chunk should have balanced tags
        assert chunk.count("<p>") == chunk.count("</p>"), \
            f"Chunk {i} has unbalanced <p> tags"
    
    print("PASS")


def test_prepare_chunks_multiple_sections():
    """Test chunking with multiple sections"""
    print("\n--- Test: Multiple Sections ---")
    
    body = """<section>
<p>Section 1 paragraph 1.</p>
<p>Section 1 paragraph 2.</p>
</section>
<section>
<p>Section 2 paragraph 1.</p>
<p>Section 2 paragraph 2.</p>
</section>"""
    
    sections = fb2.prepare_chunks(body, max_len_chunk=1000)
    
    print(f"Number of sections: {len(sections)}")
    assert len(sections) == 2, f"Expected 2 sections, got {len(sections)}"
    
    for s_idx, section_chunks in enumerate(sections):
        print(f"  Section {s_idx}: {len(section_chunks)} chunks")
        for c_idx, chunk in enumerate(section_chunks):
            print(f"    Chunk {c_idx}: {chunk[:40]}...")
    
    print("PASS")


def test_adjust_for_tag_boundary():
    """Test that we don't split inside a tag"""
    print("\n--- Test: Adjust for Tag Boundary ---")
    
    text = "<p>Text</p><emphasis>More"
    # Position inside <emphasis>
    pos = len("<p>Text</p><emphas")
    
    adjusted = fb2._adjust_for_tag_boundary(text, pos)
    print(f"Text: '{text}'")
    print(f"Original pos: {pos}, Adjusted: {adjusted}")
    print(f"Char at adjusted-1: '{text[adjusted-1] if adjusted <= len(text) else 'N/A'}'")
    
    # Should be after the tag
    assert adjusted > pos or adjusted == len(text), "Should move past tag boundary"
    print("PASS")


def main():
    """Run all chunking tests"""
    print("=" * 50)
    print("Running FB2 Chunking Tests")
    print("=" * 50)
    
    tests = [
        test_find_chunk_boundary,
        test_ensure_balanced_tags,
        test_ensure_balanced_tags_already_balanced,
        test_prepare_chunks_basic,
        test_prepare_chunks_multiple_sections,
        test_adjust_for_tag_boundary,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
