"""A5: non-standard LLM category must not crash vocabulary saving."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import _save_vocabulary_formatted


def test_save_vocabulary_nonstandard_category(tmp_path):
    translated = json.dumps({"terms": [
        {"source": "Alice", "target": "Alisa", "category": "MAGIC_CREATURE"}
    ]})
    dict_file = str(tmp_path / "TestBook.dic")
    _save_vocabulary_formatted(translated, dict_file, "Alice [MAGIC_CREATURE]")
    with open(dict_file, encoding="utf-8") as f:
        content = f.read()
    assert "Alice = Alisa" in content
