# Test for missing get_formatted_vocab_for_chunk method

"""
Test that TranslationEngine has required method get_formatted_vocab_for_chunk.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import TranslationEngine
from src.config import Config

def test_get_formatted_vocab_for_chunk_exists():
    """Test that get_formatted_vocab_for_chunk method exists."""
    config = Config()
    engine = TranslationEngine(output_tfile="/tmp/test_output.txt", book_path=None)
    
    # Check method exists
    assert hasattr(engine, 'get_formatted_vocab_for_chunk'), \
        "TranslationEngine must have get_formatted_vocab_for_chunk method"
    
    # Check method returns string
    result = engine.get_formatted_vocab_for_chunk("test chunk", 0, 0)
    assert isinstance(result, str), \
        f"get_formatted_vocab_for_chunk should return str, got {type(result)}"
    
    print("✓ get_formatted_vocab_for_chunk exists and returns string")

def test_get_vocab_dict_for_chunk_returns_dict():
    """Test that get_vocab_dict_for_chunk returns dict."""
    config = Config()
    engine = TranslationEngine(output_tfile="/tmp/test_output.txt", book_path=None)
    
    # Check method exists
    assert hasattr(engine, 'get_vocab_dict_for_chunk'), \
        "TranslationEngine must have get_vocab_dict_for_chunk method"
    
    # Check method returns dict
    result = engine.get_vocab_dict_for_chunk("test chunk", 0, 0)
    assert isinstance(result, dict), \
        f"get_vocab_dict_for_chunk should return dict, got {type(result)}"
    
    print("✓ get_vocab_dict_for_chunk exists and returns dict")

def test_get_vocab_entries_for_chunk_returns_list():
    """Test that get_vocab_entries_for_chunk returns list."""
    config = Config()
    engine = TranslationEngine(output_tfile="/tmp/test_output.txt", book_path=None)
    
    # Check method exists
    assert hasattr(engine, 'get_vocab_entries_for_chunk'), \
        "TranslationEngine must have get_vocab_entries_for_chunk method"
    
    # Check method returns list
    result = engine.get_vocab_entries_for_chunk("test chunk", 0, 0)
    assert isinstance(result, list), \
        f"get_vocab_entries_for_chunk should return list, got {type(result)}"
    
    print("✓ get_vocab_entries_for_chunk exists and returns list")

if __name__ == "__main__":
    print("Running TranslationEngine method tests...")
    
    try:
        test_get_formatted_vocab_for_chunk_exists()
    except AssertionError as e:
        print(f"✗ test_get_formatted_vocab_for_chunk_exists FAILED: {e}")
    
    try:
        test_get_vocab_dict_for_chunk_returns_dict()
    except AssertionError as e:
        print(f"✗ test_get_vocab_dict_for_chunk_returns_dict FAILED: {e}")
    
    try:
        test_get_vocab_entries_for_chunk_returns_list()
    except AssertionError as e:
        print(f"✗ test_get_vocab_entries_for_chunk_returns_list FAILED: {e}")
    
    print("\nAll tests completed!")
