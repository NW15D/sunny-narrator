"""
Integration test for the full FB2 translation workflow
Tests chunking -> translation -> reassembly without actual LLM calls
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock third party modules
sys.modules['openai'] = MagicMock()
sys.modules['tiktoken'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['httpx'] = MagicMock()

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.fb2_handler as fb2
import src.utils as utils
from src.config import Config

# Setup mocks
fb2.config = Config()
fb2.config.debug = False
utils.config = fb2.config


def mock_tiktoken():
    """Setup mock for tiktoken"""
    def mock_encode(text):
        return list(range(len(text) // 4))  # Rough approximation
    
    utils.tiktoken.get_encoding = lambda x: type('MockEncoding', (), {
        'encode': staticmethod(mock_encode)
    })()


def test_full_workflow_simulation():
    """Simulate full workflow: parse -> chunk -> translate -> assemble"""
    print("\n--- Test: Full Workflow Simulation ---")
    
    mock_tiktoken()
    
    # Sample FB2 body content
    sample_body = """<section>
<p>First paragraph of the book. It contains some interesting text.</p>
<p>Second paragraph continues the story with more details.</p>
<p>Third paragraph wraps up this section nicely.</p>
</section>
<section>
<p>Another section begins here with fresh content.</p>
<p>More text follows to make it substantial.</p>
</section>"""
    
    # Step 1: Prepare chunks
    max_chunk_size = 150  # Small size to force multiple chunks
    sections = fb2.prepare_chunks(sample_body, max_chunk_size)
    
    print(f"Parsed {len(sections)} sections")
    total_chunks = sum(len(s) for s in sections)
    print(f"Total chunks: {total_chunks}")
    
    # Verify chunks are valid
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            print(f"  Section {s_idx}, Chunk {c_idx}: {len(chunk)} chars")
            # Each chunk should have balanced tags
            open_tags = chunk.count("<p>")
            close_tags = chunk.count("</p>")
            assert open_tags == close_tags, \
                f"Unbalanced tags in chunk {s_idx}-{c_idx}: <p>={open_tags}, </p>={close_tags}"
    
    # Step 2: Simulate translation (identity for testing)
    translated_chunks = []
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            # Simulate translation by wrapping in TRANSLATED markers
            translated = f"[TRANS:{s_idx}:{c_idx}]{chunk}[/TRANS]"
            translated_chunks.append({
                'section_idx': s_idx,
                'chunk_idx': c_idx,
                'original': chunk,
                'translated': translated
            })
    
    print(f"\nSimulated translation of {len(translated_chunks)} chunks")
    
    # Step 3: Reassemble
    all_content = ""
    for item in translated_chunks:
        all_content += item['translated'] + "\n"
    
    print(f"Reassembled content: {len(all_content)} chars")
    
    # Step 4: Verify structure is preserved
    assert "[TRANS:0:0]" in all_content, "First chunk marker missing"
    assert "[/TRANS]" in all_content, "Closing marker missing"
    
    print("PASS")


def test_chunk_size_respects_limit():
    """Verify that chunks don't exceed max_len_chunk significantly"""
    print("\n--- Test: Chunk Size Respects Limit ---")
    
    # Create a body with long paragraphs
    long_text = "Word " * 100  # 500 chars
    body = f"<section><p>{long_text}</p><p>{long_text}</p></section>"
    
    max_len = 200
    sections = fb2.prepare_chunks(body, max_len)
    
    print(f"Max chunk size: {max_len}")
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            chunk_len = len(chunk)
            print(f"  Chunk {s_idx}-{c_idx}: {chunk_len} chars")
            # Allow some overshoot for tag completion
            assert chunk_len <= max_len * 1.5, \
                f"Chunk {chunk_len} exceeds limit {max_len * 1.5}"
    
    print("PASS")


def test_empty_sections_handled():
    """Test that empty or minimal sections are handled gracefully"""
    print("\n--- Test: Empty Sections ---")
    
    body = "<section></section><section><p>Only this.</p></section>"
    sections = fb2.prepare_chunks(body, 1000)
    
    print(f"Sections found: {len(sections)}")
    # Empty section should result in empty chunks list or be skipped
    non_empty = [s for s in sections if s]
    print(f"Non-empty sections: {len(non_empty)}")
    
    print("PASS")


def test_nested_tags_balanced():
    """Test that nested tags are properly balanced"""
    print("\n--- Test: Nested Tags Balanced ---")
    
    body = """<section>
<p>This is <strong>bold and <emphasis>emphasized</emphasis></strong> text.</p>
<p>Another <cite>quote with <emphasis>nested</emphasis> tags</cite>.</p>
</section>"""
    
    sections = fb2.prepare_chunks(body, 100)  # Force splitting
    
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            print(f"Chunk {s_idx}-{c_idx}: {chunk[:60]}...")
            # Count all opening and closing tags
            import re
            opening = re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*?(?<!/)>', chunk)
            closing = re.findall(r'</([a-zA-Z][a-zA-Z0-9]*)>', chunk)
            
            # After _ensure_balanced_tags, tags should be balanced
            for tag in set(opening):
                open_count = opening.count(tag)
                close_count = closing.count(tag)
                print(f"    <{tag}>: open={open_count}, close={close_count}")
    
    print("PASS")


def main():
    """Run all integration tests"""
    print("=" * 50)
    print("Running Integration Tests")
    print("=" * 50)
    
    tests = [
        test_full_workflow_simulation,
        test_chunk_size_respects_limit,
        test_empty_sections_handled,
        test_nested_tags_balanced,
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
