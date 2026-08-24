#!/usr/bin/env python3
"""
Test LLM response parsing functionality.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.vocabulary_manager import VocabularyManager


def test_json_array_parsing():
    """Test parsing of JSON array responses from LLM."""
    print("Testing JSON array response parsing...")
    
    json_response = '''[
        {
            "source": "New York, NY",
            "target": "Нью-Йорк, штат Нью-Йорк",
            "category": "LOC"
        },
        {
            "source": "Dr. John Smith",
            "target": "Доктор Джон Смит", 
            "category": "PERSON"
        },
        {
            "source": "Artificial Intelligence",
            "target": "Искусственный Интеллект",
            "category": "TERM"
        }
    ]'''
    
    with tempfile.TemporaryDirectory() as temp_dir:
        dummy_book = os.path.join(temp_dir, "dummy.txt")
        with open(dummy_book, 'w', encoding='utf-8') as f:
            f.write("Dummy\n")
        
        manager = VocabularyManager(dummy_book)
        manager.dict_file = os.path.join(temp_dir, "output.dic")
        
        # Parse the response
        count = manager._parse_and_append_chunk(json_response, 1, 1)
        
        print(f"Parsed {count} entries from JSON array")
        
        if count != 3:
            print(f"❌ FAIL: Expected 3 entries, got {count}")
            assert False
        
        # Verify the output file was created with CSV format
        if not os.path.exists(manager.dict_file):
            print("❌ FAIL: Output file not created")
            assert False
        
        with open(manager.dict_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print("Output file content:")
            print(content)
        
        # Load back and verify
        loaded_vocab = manager._load_from_file()
        if len(loaded_vocab) != 3:
            print(f"❌ FAIL: Reload failed - expected 3, got {len(loaded_vocab)}")
            assert False
        
        expected_sources = {"New York, NY", "Dr. John Smith", "Artificial Intelligence"}
        actual_sources = {entry.source for entry in loaded_vocab.values()}
        
        if expected_sources != actual_sources:
            print(f"❌ FAIL: Sources don't match after roundtrip")
            print(f"Expected: {expected_sources}")
            print(f"Actual:   {actual_sources}")
            assert False
        
        print("✅ PASS: JSON array parsing works correctly!")


def main():
    success = test_json_array_parsing()
    
    if success:
        print("\n🎉 SUCCESS: LLM JSON response parsing works correctly!")
        print("The system can handle structured JSON responses from LLMs.")
    else:
        print("\n❌ FAILURE: LLM response parsing needs attention.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)