from src.ner import _merge_overlapping_entities

def test_merge_overlapping_entities_case_insensitive_fail_on_wrong_count():
    """
    Test that when entities have different cases/categories, 
    we keep the one with the highest count regardless of input order.
    """
    # Input with lower count first
    entities = [
        ("Gant", "PERSON", 3),
        ("gant", "ORG", 5),
    ]
    result = _merge_overlapping_entities(entities)
    
    # Should merge to single entry and keep the one with count 5
    assert len(result) == 1
    assert result[0][2] == 5
    assert result[0][0].lower() == "gant"

def test_merge_overlapping_entities_substring_regardless_of_case():
    """
    Test that substring match works even if case is different.
    """
    entities = [
        ("CENTURION", "ORG", 10),
        ("centurions", "ORG", 2),
    ]
    result = _merge_overlapping_entities(entities)
    assert len(result) == 1
    # Should keep longest form
    assert result[0][0].lower() == "centurions"

if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__]))
