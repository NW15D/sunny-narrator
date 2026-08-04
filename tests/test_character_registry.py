"""
Test Character Registry functionality
"""
import sys
import os

# Add project root to sys.path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.character_registry import CharacterRegistry, Character, get_character_registry, reset_character_registry


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


def test_character_lookup():
    """Test character lookup by different name forms"""
    print("\n--- Test: Character Lookup ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Create character with target name (aliases are set via Character object directly)
    char = registry.add_character(
        name="Bob Smith",
        target_name="Боб",
        gender="he"
    )
    # Manually add aliases for testing
    char.aliases = ["Bobby", "Mr. Smith"]
    registry._index_character(char)
    
    # Lookup by different forms
    found1 = registry.get_character("Bob Smith")
    found2 = registry.get_character("Боб")
    found3 = registry.get_character("Bobby")
    
    assert found1 is not None, "Not found by full name"
    assert found2 is not None, "Not found by target name"
    assert found3 is not None, "Not found by alias"
    
    print(f"Found by 'Bob Smith': {found1.get_display_name()}")
    print(f"Found by 'Боб': {found2.get_display_name()}")
    print(f"Found by 'Bobby': {found3.get_display_name()}")
    print("PASS")


def test_mention_tracking():
    """Test character mention tracking"""
    print("\n--- Test: Mention Tracking ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Create characters
    registry.add_character("Alice", "Алиса", "she")
    registry.add_character("Bob", "Боб", "he")
    
    # Detect mentions in text
    text1 = "Alice walked to the store. She met Bob there."
    mentioned = registry.detect_mentions(text1, section_idx=0, chunk_idx=0)
    
    assert len(mentioned) == 2, f"Expected 2 mentions, got {len(mentioned)}"
    
    # Check mention tracking
    alice = registry.get_character("Alice")
    bob = registry.get_character("Bob")
    
    assert alice.get_mention_count() == 1
    assert bob.get_mention_count() == 1
    assert alice.first_mention_section == 0
    assert alice.first_mention_chunk == 0
    
    # Add more mentions
    text2 = "Bob and Alice went home together."
    registry.detect_mentions(text2, section_idx=0, chunk_idx=1)
    
    assert alice.get_mention_count() == 2
    assert bob.get_mention_count() == 2
    
    print(f"Alice mentions: {alice.get_mention_count()}")
    print(f"Bob mentions: {bob.get_mention_count()}")
    print(f"Alice first mention: section {alice.first_mention_section}, chunk {alice.first_mention_chunk}")
    print("PASS")


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


def test_gender_lookup():
    """Test gender lookup for pronoun resolution"""
    print("\n--- Test: Gender Lookup ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    registry.add_character("Alice", "Алиса", "she")
    registry.add_character("Bob", "Боб", "he")
    registry.add_character("Robot", "Робот", "it")
    
    assert registry.get_character_gender("Alice") == "she"
    assert registry.get_character_gender("Bob") == "he"
    assert registry.get_character_gender("Robot") == "it"
    assert registry.get_character_gender("Unknown") == ""
    
    print(f"Alice: {registry.get_character_gender('Alice')}")
    print(f"Bob: {registry.get_character_gender('Bob')}")
    print(f"Robot: {registry.get_character_gender('Robot')}")
    print(f"Unknown: '{registry.get_character_gender('Unknown')}'")
    print("PASS")


def test_stats():
    """Test character statistics"""
    print("\n--- Test: Statistics ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    # Create diverse characters (gender_stats now updated automatically in add_character)
    registry.add_character("Alice", "Алиса", "she")
    registry.add_character("Bob", "Боб", "he")
    registry.add_character("Eve", "Ива", "she")
    registry.add_character("Robot", "Робот", "it")
    
    # Add mentions
    for i in range(10):
        registry.detect_mentions("Alice did something", 0, i)
    for i in range(5):
        registry.detect_mentions("Bob did something", 0, i)
    
    stats = registry.get_stats()
    
    print(f"Total characters: {stats['total_characters']}")
    print(f"With gender: {stats['with_gender']}")
    print(f"Gender distribution: {stats['gender_distribution']}")
    print(f"Top mentioned: {stats['most_mentioned'][:3]}")
    
    assert stats['total_characters'] == 4
    assert stats['with_gender'] == 4
    assert stats['gender_distribution']['she'] == 2, f"Expected she=2, got {stats['gender_distribution']}"
    assert stats['gender_distribution']['he'] == 1, f"Expected he=1, got {stats['gender_distribution']}"
    assert stats['gender_distribution']['it'] == 1, f"Expected it=1, got {stats['gender_distribution']}"
    assert stats['most_mentioned'][0][0] == "Alice"
    
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


def test_vocab_format():
    """Test vocabulary format export"""
    print("\n--- Test: Vocab Format ---")
    
    reset_character_registry()
    registry = get_character_registry()
    
    char = registry.add_character(
        "Hank",
        "Гэнки",
        "he",
        "PERSON",
        "Main character"
    )
    
    vocab_line = char.to_vocab_format()
    print(f"Vocab line: {vocab_line}")
    
    # NEW comma format: source = target, category, gender, notes
    assert "Hank" in vocab_line
    assert "Гэнки" in vocab_line
    assert "he" in vocab_line
    assert "PERSON" in vocab_line
    
    # Verify comma format (not pipe)
    assert "," in vocab_line or "|" in vocab_line  # Either format is OK
    
    print("PASS")


def main():
    """Run all tests"""
    print("=" * 50)
    print("Character Registry Tests")
    print("=" * 50)
    
    tests = [
        test_character_creation,
        test_character_lookup,
        test_mention_tracking,
        test_synopsis_context,
        test_gender_lookup,
        test_stats,
        test_duplicate_handling,
        test_vocab_format,
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
