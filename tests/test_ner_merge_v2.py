from src.ner import _merge_overlapping_entities

def test_merge_equal_length_prefers_higher_count():
    """
    Test that when entities have the same length, the one with the 
    higher count is preferred.
    """
    entities = [
        ("Gant", "PERSON", 3),
        ("gant", "ORG", 5),
    ]
    result = _merge_overlapping_entities(entities)
    # Current code might return Gant (3) if it's first in the list
    # because it only sorts by length.
    assert len(result) == 1
    assert result[0][2] == 5
    assert result[0][0].lower() == "gant"

def test_merge_substring_prefers_longest_form():
    """
    Test that the longest form is still preferred for substrings, 
    even if it has a lower count (as per docstring).
    """
    entities = [
        ("John Smith", "PERSON", 2),
        ("John", "PERSON", 10),
    ]
    result = _merge_overlapping_entities(entities)
    assert len(result) == 1
    assert result[0][0] == "John Smith"

if __name__ == "__main__":
    import pytest
    import sys
    # Run via pytest for better output
    sys.exit(pytest.main([__file__]))
