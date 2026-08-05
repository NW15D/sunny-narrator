"""Roundtrip test: writer emits format the reader can parse."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.vocabulary_manager import VocabularyManager


def test_writer_reader_roundtrip():
    """Entries written by _parse_and_append_chunk must be readable by _load_from_file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dic_path = os.path.join(tmpdir, "TestBook.dic")

        # Create a VocabularyManager pointing at our temp .dic
        vm = VocabularyManager.__new__(VocabularyManager)
        vm.dict_file = dic_path
        vm.book_name = "TestBook"
        vm.vocab = {}

        # Write header (simulates what the NER flow does before appending)
        with open(dic_path, 'w', encoding='utf-8') as f:
            f.write(f"# Vocabulary for {vm.book_name}\n")
            f.write("# Format: source = target, category, gender, notes\n")
            f.write("# Generated automatically by NER\n\n")

        # Simulate _parse_and_append_chunk output directly
        # (avoids needing a live NER/LLM call)
        valid_terms = [
            {"source": "Alice", "target": "Алиса", "category": "PERSON"},
            {"source": "Wonderland", "target": "Страна Чудес", "category": "LOC"},
            {"source": "Queen's Court", "target": "Двор Королевы", "category": "ORG"},
        ]

        with open(dic_path, 'a', encoding='utf-8') as f:
            f.write("\n# --- Translated Terms (Format: source = target, category, gender, notes) ---\n")
            for term in valid_terms:
                f.write(f"{term['source']} = {term['target']}, {term['category']}, , \n")

        # Now load via the reader
        loaded = vm._load_from_file()

        # Must have loaded all entries
        assert len(loaded) > 0, "Reader loaded 0 entries — format mismatch!"
        assert len(loaded) == len(valid_terms), (
            f"Expected {len(valid_terms)} entries, got {len(loaded)}"
        )

        # Verify data integrity
        for term in valid_terms:
            key = term["source"].replace(' ', '_').lower()
            assert key in loaded, f"Missing entry: {term['source']} (key={key})"
            entry = loaded[key]
            assert entry.source == term["source"]
            assert entry.target == term["target"]
            assert entry.category == term["category"]


if __name__ == "__main__":
    test_writer_reader_roundtrip()
    print("PASS: roundtrip test passed")
