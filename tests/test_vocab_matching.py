import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to sys.path so we can import src
sys.path.append("/home/neo/prj/sunny-narrator")

from src.ner import find_matching_words_with_cosine_similarity, find_matching_words_with_cosine_similarity_cpu

@pytest.fixture(autouse=True)
def mock_config():
    """Mock the config object used in src.ner to avoid actual config loading."""
    with patch("src.ner.config") as mock:
        mock.debug = False
        mock.nermodel = "en_core_web_sm" # use a small model for testing
        yield mock

def test_exact_text_match():
    """Test that exact substring match finds dictionary terms in chunk."""
    # Dictionary with terms that appear in text
    vocab = {
        "bonded": {"en": "bonded"},
        "hooder": {"en": "hooder"},
        "crushed": {"en": "crushed"}
    }
    
    # Chunk text containing these terms
    text = "The bonded soldier crushed the enemy's weapon. His hooder glowed."
    
    # Use CPU version to avoid CUDA issues in test environment
    matched = find_matching_words_with_cosine_similarity_cpu(text, vocab, "en", threshold=0.8)
    
    # MUST find exact matches regardless of cosine similarity
    assert "bonded" in matched
    assert "crushed" in matched
    assert "hooder" in matched

def test_exact_text_match_cpu():
    """Test CPU version for exact substring match."""
    vocab = {
        "bonded": {"en": "bonded"},
        "hooder": {"en": "hooder"}
    }
    
    text = "The bonded soldier with his hooder weapon."
    
    matched = find_matching_words_with_cosine_similarity_cpu(text, vocab, "en", threshold=0.8)
    
    assert "bonded" in matched
    assert "hooder" in matched

def test_multi_word_term_match():
    """Test exact match for multi-word terms like 'John Smith'."""
    vocab = {
        "john_smith": {"en": "John Smith"},
        "mad_hatter": {"en": "Mad Hatter"}
    }
    
    text = "John Smith met the Mad Hatter at the party."
    
    # Use CPU version to avoid CUDA issues in test environment
    matched = find_matching_words_with_cosine_similarity_cpu(text, vocab, "en", threshold=0.8)
    
    # Multi-word terms should be matched as substrings
    assert "John Smith" in matched
    assert "Mad Hatter" in matched

def test_no_match_for_missing_terms():
    """Test that terms NOT in text are not matched."""
    vocab = {
        "alice": {"en": "Alice"},
        "wonderland": {"en": "Wonderland"},
        "rabbit": {"en": "Rabbit"}
    }
    
    text = "Alice went to a strange place. No rabbits here."
    
    # Use CPU version to avoid CUDA issues in test environment
    matched = find_matching_words_with_cosine_similarity_cpu(text, vocab, "en", threshold=0.8)
    
    # Alice is in text -> match
    assert "Alice" in matched
    # Wonderland NOT in text -> no match
    assert "Wonderland" not in matched
    # Rabbit NOT in text (only "rabbits" with 's') -> no match
    assert "Rabbit" not in matched


def test_format_standard_no_trailing_commas():
    """Test that _format_standard() removes trailing empty commas."""
    from src.vocabulary_manager import VocabEntry, VocabularyManager
    
    # Create mock manager (no file needed)
    manager = VocabularyManager.__new__(VocabularyManager)
    
    # Entries with empty fields
    entries = [
        VocabEntry(source="bonded", target="связанный", category="", gender="", notes=""),
        VocabEntry(source="hooder", target="капюшонник", category="PERSON", gender="он", notes="инопланетное существо"),
        VocabEntry(source="crushed", target="раздавил", category="", gender="", notes=""),
    ]
    
    formatted = manager._format_standard(entries)
    lines = formatted.split('\n')
    
    # No trailing commas for entries without metadata
    assert lines[0] == "bonded = связанный", f"Got: {lines[0]}"
    assert lines[2] == "crushed = раздавил", f"Got: {lines[2]}"
    
    # Full metadata for entries with data
    assert lines[1] == "hooder = капюшонник, PERSON, он, инопланетное существо", f"Got: {lines[1]}"


def test_format_hunyuan_no_trailing_commas():
    """Test Hunyuan format (source=target(category))."""
    from src.vocabulary_manager import VocabEntry, VocabularyManager
    
    manager = VocabularyManager.__new__(VocabularyManager)
    
    entries = [
        VocabEntry(source="bonded", target="связанный", category="", gender="", notes=""),
        VocabEntry(source="Alice", target="Алиса", category="PERSON", gender="", notes=""),
    ]
    
    formatted = manager._format_hunyuan(entries)
    
    # Format: source=target(category) if category exists
    lines = formatted.split(' | ')
    
    # bonded has no category - should be bonded=связанный
    assert "bonded=связанный" in formatted
    
    # Alice has PERSON category - should be Alice=Алиса(PERSON)
    assert "Alice=Алиса(PERSON)" in formatted


def test_format_gemma_no_trailing_commas():
    """Test Gemma format (source → target, category)."""
    from src.vocabulary_manager import VocabEntry, VocabularyManager
    
    manager = VocabularyManager.__new__(VocabularyManager)
    
    entries = [
        VocabEntry(source="bonded", target="связанный", category="", gender="", notes=""),
        VocabEntry(source="Alice", target="Алиса", category="PERSON", gender="", notes=""),
    ]
    
    formatted = manager._format_gemma(entries)
    lines = formatted.split('\n')
    
    # bonded has no category - should be "  bonded → связанный"
    assert "bonded → связанный" in formatted
    assert "bonded → связанный, " not in formatted  # No trailing comma
    
    # Alice has PERSON category - should be "  Alice → Алиса, PERSON"
    assert "Alice → Алиса, PERSON" in formatted
