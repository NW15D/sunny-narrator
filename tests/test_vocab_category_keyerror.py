"""A5: non-standard LLM category must not crash vocabulary saving."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.vocabulary_manager import VocabularyManager


def test_save_vocabulary_nonstandard_category(tmp_path):
    translated = json.dumps({"terms": [
        {"source": "Alice", "target": "Alisa", "category": "MAGIC_CREATURE"}
    ]})
    dict_file = str(tmp_path / "TestBook.dic")
    manager = VocabularyManager(str(tmp_path / "TestBook.fb2"), dict_file=dict_file)
    assert manager._parse_and_append_chunk(translated, 1, 1) == 1
    with open(dict_file, encoding="utf-8") as f:
        content = f.read()
    assert "Alice = Alisa,TERM" in content
