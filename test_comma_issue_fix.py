#!/usr/bin/env python3
"""
Focused test to verify the comma handling issue is fixed.

This test specifically addresses the original problem where vocabulary entries
containing commas would result in 0 records being loaded.
"""

import os
import sys
import csv
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.vocabulary_manager import VocabularyManager


def test_comma_issue_fix():
    """Test that entries with commas don't result in 0 records."""
    print("Testing comma handling fix...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create dictionary file with commas in source, target, and notes fields
        dict_file = os.path.join(temp_dir, "test.dic")
        
        test_data = [
            ["New York, NY", "Нью-Йорк, штат Нью-Йорк", "LOC", "", "Major US city"],
            ["Dr. Smith, PhD", "Доктор Смит, доктор наук", "PERSON", "he", "Expert in AI, from MIT"],
            ["Paris, France", "Париж, Франция", "LOC", "", "European capital"]
        ]
        
        # Write using proper CSV formatting
        with open(dict_file, 'w', encoding='utf-8') as f:
            f.write("# Test for comma issue\n")
            f.write("# source,target,category,gender,notes\n\n")
            
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            for row in test_data:
                writer.writerow(row)
        
        # Verify file content
        with open(dict_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print("Dictionary content:")
            print(content)
        
        # Create dummy book file
        dummy_book = os.path.join(temp_dir, "dummy.txt")
        with open(dummy_book, 'w', encoding='utf-8') as f:
            f.write("Dummy content\n")
        
        # Load vocabulary
        manager = VocabularyManager(dummy_book)
        manager.dict_file = dict_file
        vocab = manager._load_from_file()
        
        print(f"\nLoaded {len(vocab)} entries")
        
        # The critical test: should NOT be 0 records
        if len(vocab) == 0:
            print("❌ FAIL: Still getting 0 records with commas!")
            return False
        
        if len(vocab) != len(test_data):
            print(f"❌ FAIL: Expected {len(test_data)} entries, got {len(vocab)}")
            return False
        
        # Verify specific entries with commas
        expected_sources = {"New York, NY", "Dr. Smith, PhD", "Paris, France"}
        actual_sources = {entry.source for entry in vocab.values()}
        
        if expected_sources != actual_sources:
            print(f"❌ FAIL: Source mismatch!")
            print(f"Expected: {expected_sources}")
            print(f"Actual:   {actual_sources}")
            return False
        
        print("✅ PASS: Comma handling issue is FIXED!")
        print(f"   - Successfully loaded {len(vocab)} entries with commas")
        print(f"   - All source terms with commas preserved correctly")
        return True


def main():
    success = test_comma_issue_fix()
    
    if success:
        print("\n🎉 SUCCESS: The 0-record issue with commas has been resolved!")
        print("The vocabulary manager now correctly handles CSV format with commas in any field.")
    else:
        print("\n❌ FAILURE: The comma issue is NOT resolved.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)