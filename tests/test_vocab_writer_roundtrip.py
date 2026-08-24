"""E3: dictionary writer must CSV-quote fields so commas survive the roundtrip."""
import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.vocabulary_manager import VocabularyManager


def test_writer_roundtrip_preserves_commas():
    with tempfile.TemporaryDirectory() as td:
        book = os.path.join(td, "b.txt")
        with open(book, "w", encoding="utf-8") as f:
            f.write("dummy\n")
        m = VocabularyManager(book)
        m.dict_file = os.path.join(td, "t.dic")
        with open(m.dict_file, "w", encoding="utf-8") as f:
            f.write("# hdr\n\n")
        js = json.dumps([{"source": "New York, NY",
                          "target": "Нью-Йорк, штат Нью-Йорк",
                          "category": "LOC"}], ensure_ascii=False)
        n = m._parse_and_append_chunk(js, 1, 1)
        assert n == 1
        v = m._load_from_file()
        assert len(v) == 1
        entry = next(iter(v.values()))
        assert entry.source == "New York, NY"
        assert entry.target == "Нью-Йорк, штат Нью-Йорк"
        assert entry.category == "LOC"
