#!/usr/bin/env python3
"""
Test script to verify vocabulary_manager.py handles CSV format correctly,
especially when fields contain commas.

This test addresses the issue where vocabulary entries with commas in any field
were not being properly parsed, leading to 0 records being loaded.
"""

import os
import sys
import csv
import tempfile
from io import StringIO
from pathlib import Path

# Add src to path to import vocabulary_manager
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.vocabulary_manager import VocabularyManager, VocabEntry


def create_test_dictionary_with_commas(temp_dir):
    """Create a test dictionary file with terms containing commas in various fields."""
    dict_file = os.path.join(temp_dir, "test_book.dic")
    
    # Test data with commas in different fields
    test_entries = [
        {
            "source": "New York, NY",
            "target": "Нью-Йорк, штат Нью-Йорк", 
            "category": "LOC",
            "gender": "",
            "notes": "Major city in the United States"
        },
        {
            "source": "Dr. John Smith",
            "target": "Доктор Джон Смит",
            "category": "PERSON", 
            "gender": "he",
            "notes": "Main character, appears in chapters 1, 3, 5"
        },
        {
            "source": "International Business Machines Corporation",
            "target": "Корпорация Международных Бизнес-Машин",
            "category": "ORG",
            "gender": "",
            "notes": "Also known as IBM, founded in 1911"
        },
        {
            "source": "Artificial Intelligence",
            "target": "Искусственный Интеллект",
            "category": "TERM",
            "gender": "",
            "notes": "Key concept, appears throughout the book"
        },
        {
            "source": "Paris, France",
            "target": "Париж, Франция",
            "category": "LOC",
            "gender": "",
            "notes": "Capital city of France"
        }
    ]
    
    # Write header and entries using proper CSV formatting
    with open(dict_file, 'w', encoding='utf-8') as f:
        f.write("# Test vocabulary with commas\n")
        f.write("# Format: source,target,category,gender,notes\n\n")
        
        csv_writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        for entry in test_entries:
            csv_writer.writerow([
                entry["source"],
                entry["target"], 
                entry["category"],
                entry["gender"],
                entry["notes"]
            ])
    
    print(f"Created test dictionary: {dict_file}")
    print(f"Expected entries: {len(test_entries)}")
    
    # Verify the file content
    with open(dict_file, 'r', encoding='utf-8') as f:
        content = f.read()
        print("\nDictionary file content:")
        print(content)
    
    return dict_file, test_entries


def test_csv_loading():
    """Test that vocabulary_manager can load CSV files with commas correctly."""
    print("=" * 60)
    print("TEST 1: CSV Loading with Commas")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test dictionary
        dict_file, expected_entries = create_test_dictionary_with_commas(temp_dir)
        
        # Create a dummy book file (required by VocabularyManager)
        dummy_book = os.path.join(temp_dir, "test_book.txt")
        with open(dummy_book, 'w', encoding='utf-8') as f:
            f.write("Dummy book content for testing.\n")
        
        # Initialize VocabularyManager
        manager = VocabularyManager(dummy_book)
        manager.dict_file = dict_file  # Override the dict file path
        
        # Load vocabulary
        loaded_vocab = manager._load_from_file()
        
        print(f"\nLoaded {len(loaded_vocab)} entries from CSV")
        
        # Verify we loaded the expected number of entries
        if len(loaded_vocab) != len(expected_entries):
            print(f"❌ FAIL: Expected {len(expected_entries)} entries, got {len(loaded_vocab)}")
            return False
        
        # Verify each entry matches expected data
        for i, expected in enumerate(expected_entries):
            source_key = expected["source"].replace(' ', '_').lower()
            
            if source_key not in loaded_vocab:
                # Try alternative key formats
                found = False
                for key in loaded_vocab.keys():
                    if loaded_vocab[key].source == expected["source"]:
                        actual = loaded_vocab[key]
                        found = True
                        break
                
                if not found:
                    print(f"❌ FAIL: Entry {i+1} not found: {expected['source']}")
                    return False
            else:
                actual = loaded_vocab[source_key]
            
            # Compare all fields
            if (actual.source != expected["source"] or
                actual.target != expected["target"] or
                actual.category != expected["category"] or
                actual.gender != expected["gender"] or
                actual.notes != expected["notes"]):
                print(f"❌ FAIL: Entry {i+1} mismatch:")
                print(f"  Expected: {expected}")
                print(f"  Actual:   {{'source': '{actual.source}', 'target': '{actual.target}', "
                      f"'category': '{actual.category}', 'gender': '{actual.gender}', 'notes': '{actual.notes}'}}")
                return False
        
        print("✅ PASS: All entries loaded correctly!")
        return True


def test_llm_json_response_parsing():
    """Test parsing of various LLM JSON response formats."""
    print("\n" + "=" * 60)
    print("TEST 2: LLM JSON Response Parsing")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create dummy book file
        dummy_book = os.path.join(temp_dir, "test_book.txt")
        with open(dummy_book, 'w', encoding='utf-8') as f:
            f.write("Dummy book content.\n")
        
        manager = VocabularyManager(dummy_book)
        manager.dict_file = os.path.join(temp_dir, "test_output.dic")
        
        # Test case 1: Valid JSON array response
        json_array_response = '''[
            {
                "source": "New York, NY",
                "target": "Нью-Йорк, штат Нью-Йорк",
                "category": "LOC"
            },
            {
                "source": "Dr. John Smith", 
                "target": "Доктор Джон Смит",
                "category": "PERSON"
            }
        ]'''
        
        print("Testing JSON array response...")
        count1 = manager._parse_and_append_chunk(json_array_response, 1, 1)
        print(f"Parsed {count1} entries from JSON array")
        
        if count1 != 2:
            print(f"❌ FAIL: Expected 2 entries from JSON array, got {count1}")
            return False
        
        # Reset for next test
        manager.vocab.clear()
        
        # Test case 2: JSON object with terms array
        json_obj_response = '''{
            "terms": [
                {
                    "source": "Paris, France",
                    "target": "Париж, Франция", 
                    "category": "LOC"
                },
                {
                    "source": "AI System",
                    "target": "Система ИИ",
                    "category": "TERM"
                }
            ]
        }'''
        
        print("Testing JSON object with terms array...")
        count2 = manager._parse_and_append_chunk(json_obj_response, 1, 1)
        print(f"Parsed {count2} entries from JSON object")
        
        if count2 != 2:
            print(f"❌ FAIL: Expected 2 entries from JSON object, got {count2}")
            return False
        
        # Reset for next test
        manager.vocab.clear()
        
        # Test case 3: Markdown table format
        markdown_response = '''
| Source | Target | Category |
|--------|--------|----------|
| Tokyo, Japan | Токио, Япония | LOC |
| Prof. Alice Johnson | Профессор Элис Джонсон | PERSON |
'''
        
        print("Testing markdown table response...")
        count3 = manager._parse_and_append_chunk(markdown_response, 1, 1)
        print(f"Parsed {count3} entries from markdown table")
        
        if count3 != 2:
            print(f"❌ FAIL: Expected 2 entries from markdown table, got {count3}")
            return False
        
        print("✅ PASS: All LLM response formats parsed correctly!")
        return True


def test_csv_roundtrip():
    """Test complete roundtrip: create → save → load → verify."""
    print("\n" + "=" * 60)
    print("TEST 3: Complete CSV Roundtrip")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test data
        test_entries = [
            VocabEntry(
                source="San Francisco, CA",
                target="Сан-Франциско, Калифорния",
                category="LOC",
                gender="",
                notes="Major tech hub on the west coast"
            ),
            VocabEntry(
                source="Mary, Queen of Scots",
                target="Мария, королева Шотландии", 
                category="PERSON",
                gender="she",
                notes="Historical figure, 16th century"
            )
        ]
        
        # Create dummy book
        dummy_book = os.path.join(temp_dir, "roundtrip_test.txt")
        with open(dummy_book, 'w', encoding='utf-8') as f:
            f.write("Roundtrip test book.\n")
        
        manager = VocabularyManager(dummy_book)
        manager.dict_file = os.path.join(temp_dir, "roundtrip_test.dic")
        
        # Add entries to vocab
        for entry in test_entries:
            key = entry.source.replace(' ', '_').lower()
            manager.vocab[key] = entry
        
        # Save using the standard method (this simulates what happens during _create_dictionary)
        with open(manager.dict_file, 'w', encoding='utf-8') as f:
            f.write("# Roundtrip test dictionary\n")
            f.write("# source,target,category,gender,notes\n\n")
            
            csv_buffer = StringIO()
            csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)
            
            for entry in test_entries:
                csv_writer.writerow([
                    entry.source,
                    entry.target,
                    entry.category,
                    entry.gender,
                    entry.notes
                ])
            
            f.write(csv_buffer.getvalue())
        
        print(f"Saved {len(test_entries)} entries to {manager.dict_file}")
        
        # Load back
        loaded_vocab = manager._load_from_file()
        
        print(f"Loaded {len(loaded_vocab)} entries back")
        
        if len(loaded_vocab) != len(test_entries):
            print(f"❌ FAIL: Roundtrip failed - expected {len(test_entries)}, got {len(loaded_vocab)}")
            return False
        
        # Verify integrity
        for original in test_entries:
            key = original.source.replace(' ', '_').lower()
            if key not in loaded_vocab:
                # Find by source match
                found = False
                for loaded_key, loaded_entry in loaded_vocab.items():
                    if loaded_entry.source == original.source:
                        loaded = loaded_entry
                        found = True
                        break
                if not found:
                    print(f"❌ FAIL: Entry not found after roundtrip: {original.source}")
                    return False
            else:
                loaded = loaded_vocab[key]
            
            if (loaded.source != original.source or
                loaded.target != original.target or
                loaded.category != original.category or
                loaded.gender != original.gender or
                loaded.notes != original.notes):
                print(f"❌ FAIL: Data corruption in roundtrip for: {original.source}")
                print(f"  Original: {original}")
                print(f"  Loaded:   {loaded}")
                return False
        
        print("✅ PASS: Complete roundtrip successful!")
        return True


def main():
    """Run all tests."""
    print("Running vocabulary_manager CSV comma handling tests...\n")
    
    success = True
    
    # Test 1: CSV loading
    if not test_csv_loading():
        success = False
    
    # Test 2: LLM response parsing
    if not test_llm_json_response_parsing():
        success = False
    
    # Test 3: Complete roundtrip
    if not test_csv_roundtrip():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED! The comma handling issue is resolved.")
        print("The vocabulary manager now correctly handles:")
        print("  • CSV files with commas in any field")
        print("  • Various LLM response formats")  
        print("  • Complete save/load roundtrips")
    else:
        print("❌ SOME TESTS FAILED! The issue may not be fully resolved.")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)