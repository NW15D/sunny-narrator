#!/usr/bin/env python3
"""
Test robust vocabulary parsing with various malformed LLM responses.
"""

import sys
sys.path.insert(0, 'src')

from src.ner import _parse_vocabulary_response

def test_clean_json():
    """Test clean JSON response."""
    response = '''{
        "terms": [
            {"source": "Alice", "target": "Алиса", "category": "PERSON"},
            {"source": "wonderland", "target": "Страна чудес", "category": "LOC"}
        ]
    }'''
    
    original_terms = "Alice [PERSON]\nwonderland [LOC]"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert "alice" in result
    assert result["alice"][0] == "Алиса"
    assert result["alice"][1] == "PERSON"
    assert "wonderland" in result
    print("✅ Clean JSON test passed")

def test_array_json():
    """Test array-only JSON response."""
    response = '''[
        {"source": "Bob", "target": "Боб", "category": "PERSON"},
        {"source": "London", "target": "Лондон", "category": "LOC"}
    ]'''
    
    original_terms = "Bob [PERSON]\nLondon [LOC]"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert "bob" in result
    assert result["bob"][0] == "Боб"
    assert "london" in result
    print("✅ Array JSON test passed")

def test_malformed_with_text():
    """Test JSON response with extra text."""
    response = '''Some preamble text here...
{
    "terms": [
        {"source": "Charlie", "target": "Чарли", "category": "PERSON"}
    ]
}
Some trailing text...'''
    
    original_terms = "Charlie [PERSON]"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert "charlie" in result
    assert result["charlie"][0] == "Чарли"
    print("✅ Malformed with text test passed")

def test_individual_objects():
    """Test individual JSON objects in text."""
    response = '''Here are the terms:
{"source": "David", "target": "Дэвид", "category": "PERSON"}
And another one:
{"source": "Paris", "target": "Париж", "category": "LOC"}'''
    
    original_terms = "David [PERSON]\nParis [LOC]"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert "david" in result
    assert "paris" in result
    print("✅ Individual objects test passed")

def test_fallback_csv():
    """Test fallback to CSV-like parsing."""
    response = '''Alice = Алиса
Bob = Боб, PERSON
wonderland = Страна чудес'''
    
    original_terms = "Alice\nBob [PERSON]\nwonderland"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert "alice" in result
    assert result["alice"][0] == "Алиса"
    assert "bob" in result
    assert result["bob"][1] == "PERSON"  # From original terms
    print("✅ Fallback CSV test passed")

def test_empty_response():
    """Test empty or invalid response."""
    response = "No valid response here"
    original_terms = "Test [TERM]"
    result = _parse_vocabulary_response(response, original_terms)
    
    assert len(result) == 0
    print("✅ Empty response test passed")

if __name__ == "__main__":
    test_clean_json()
    test_array_json()
    test_malformed_with_text()
    test_individual_objects()
    test_fallback_csv()
    test_empty_response()
    print("\n🎉 All robust parsing tests passed!")