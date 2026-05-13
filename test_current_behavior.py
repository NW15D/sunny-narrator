from src.ner import _merge_overlapping_entities

def test_current_behavior():
    entities = [
        ("gant", "ORG", 5),
        ("Gant", "PERSON", 3),
        ("Centurions", "ORG", 4),
        ("Centurion", "ORG", 2),
        ("centurion", "PRODUCT", 1),
    ]
    print("Input entities:", entities)
    result = _merge_overlapping_entities(entities)
    print("Resulting entities:", result)

    # Expected according to plan:
    # Gant (PERSON, 3) ?? No, wait.
    # gant (ORG, 5) and Gant (PERSON, 3) -> merge. 
    # If we keep highest count: ("gant", "ORG", 5)
    # But the plan says: "Gant = Гант, PERSON,," in expected output.
    # Let's see what the plan actually wants.
    # The plan says: "gant and Gant should merge into single entry (keep highest count form)"
    # In sample input: gant has 5, Gant has 3. So gant should be kept.
    # But in expected output: "Gant = Гант, PERSON,,". This is contradictory if it says "keep highest count form".
    # Wait, the expected output shows "Gant = Гант, PERSON,,". Maybe it means the one with the more "important" category? Or maybe I misread.
    # Let's re-read: "Expected output (after fix): Gant = Гант, PERSON,, ..."
    # In sample input: gant is ORG(5), Gant is PERSON(3). 
    # If it keeps highest count, it should be gant (ORG, 5).
    # If it keeps PERSON, why? 
    # Let's look at the other one: Centurions (ORG, 4), Centurion (ORG, 2), centurion (PRODUCT, 1).
    # Expected: "Centurion = Центурион, ORG, ,". 
    # This is the root form (Centurion) and it has the highest count among ORG forms (4 vs 2), but wait...
    # Centurions (4) + Centurion (2) = 6? No, they are distinct.
    # If we merge them, we should get one entry.
    # This is a bit ambiguous. Let's just see what the CURRENT code does.

if __name__ == "__main__":
    test_current_behavior()
