from src.ner import _merge_overlapping_entities

def test_merge_overlapping_entities_case_insensitive():
    """
    Test that entities with same name but different case 
    and different categories are merged (as per plan requirement).
    """
    entities = [
        ("gant", "ORG", 5),
        ("Gant", "PERSON", 3),
    ]
    result = _merge_overlapping_entities(entities)
    # Should merge to single entry with highest count
    assert len(result) == 1
    # Keep the one with highest count
    assert result[0][0].lower() == "gant"
    assert result[0][2] == 5

def test_merge_overlapping_entities_substring():
    """
    Test that substring entities are merged regardless of case.
    """
    entities = [
        ("Centurions", "ORG", 4),
        ("centurion", "ORG", 2),
    ]
    result = _merge_overlapping_entities(entities)
    assert len(result) == 1
    # Should keep the longest form
    assert result[0][0].lower() == "centurions"

if __name__ == "__main__":
    import sys
    # Simple runner for local testing if needed
    try:
        test_merge_overlapping_entities_case_insensitive()
        print("test_merge_overlapping_entities_case_insensitive passed")
    except Exception as e:
        print(f"test_merge_overlapping_entities_case_insensitive failed: {e}")
        sys.exit(1)

    try:
        test_merge_overlapping_entities_substring()
        print("test_merge_overlapping_entities_substring passed")
    except Exception as e:
        print(f"test_merge_overlapping_entities_substring failed: {e}")
        sys.exit(1)
