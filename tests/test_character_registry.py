"""
Test Character Registry functionality
"""
import sys

# Add project root to sys.path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.character_registry import get_character_registry, reset_character_registry


def test_character_creation():
    """Test basic character creation"""
    print("\n--- Test: Character Creation ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Create character
    char = registry.add_character(
        name="Alice",
        target_name="Алиса",
        gender="she",
        category="PERSON",
        notes="Main character"
    )
    
    assert char.name == "Alice"
    assert char.target_name == "Алиса"
    assert char.gender == "she"
    assert char.category == "PERSON"
    
    print(f"Created: {char.get_display_name()} ({char.gender})")
    print("PASS")


def test_mention_tracking():
    """detect_mentions counts every mention and remembers the first one."""
    reset_character_registry()
    registry = get_character_registry()

    alice = registry.add_character("Alice", "Алиса", "she")
    bob = registry.add_character("Bob", "Боб", "he")

    mentioned = registry.detect_mentions("Alice walked to the store. She met Bob there.",
                                         section_idx=0, chunk_idx=0)
    assert {c.name for c in mentioned} == {"Alice", "Bob"}
    assert alice.get_mention_count() == 1 and bob.get_mention_count() == 1
    assert (alice.first_mention_section, alice.first_mention_chunk) == (0, 0)

    registry.detect_mentions("Bob and Alice went home together.", section_idx=0, chunk_idx=1)
    assert alice.get_mention_count() == 2 and bob.get_mention_count() == 2
    assert (alice.first_mention_section, alice.first_mention_chunk) == (0, 0)


def test_synopsis_context():
    """Test character context line generation for synopsis"""
    print("\n--- Test: Synopsis Context ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Create characters with mentions
    registry.add_character("Alice", "Алиса", "she")
    registry.add_character("Bob", "Боб", "he")
    registry.add_character("Cat", "Кот", "it")
    
    # Simulate mentions
    registry.detect_mentions("Alice was here", 0, 0)
    registry.detect_mentions("Bob arrived", 0, 1)
    registry.detect_mentions("Alice and Bob talked", 0, 2)
    registry.detect_mentions("The Cat watched", 0, 3)
    
    # Get context line
    context = registry.get_character_context_line(0, 3)
    
    print(f"Context line: {context}")
    assert "Characters:" in context
    assert "Alice" in context or "Алиса" in context
    
    print("PASS")


def test_duplicate_handling():
    """Test that duplicate characters are handled correctly"""
    print("\n--- Test: Duplicate Handling ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Add same character twice
    char1 = registry.add_character("Alice", "Алиса", "she", notes="First note")
    char2 = registry.add_character("Alice", "Элис", "she", notes="Second note")
    
    # Should be same object
    assert char1 is char2, "Should return existing character"
    
    # First values should be preserved
    assert char1.target_name == "Алиса", "Should keep first target name"
    assert char1.notes == "First note", "Should keep first notes"
    
    print(f"Character: {char1.get_display_name()}")
    print(f"Notes: {char1.notes}")
    print("PASS")


def main():
    """Run all tests"""
    print("=" * 50)
    print("Character Registry Tests")
    print("=" * 50)
    
    tests = [
        test_character_creation,
        test_mention_tracking,
        test_synopsis_context,
        test_duplicate_handling,
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
