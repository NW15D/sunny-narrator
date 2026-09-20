"""Metadata translation must receive the book glossary (both pipelines)."""
import json
from unittest.mock import patch

from src import utils
from src.vocabulary_manager import VocabEntry


def test_block_contains_only_terms_present_in_metadata():
    entries = [
        VocabEntry(source="Harry Potter", target="Гарри Поттер", category="PERSON"),
        {"source": "Mordor", "target": "Мордор", "category": "LOC"},
    ]
    block = utils.build_metadata_vocab_block(entries, {"title": "harry potter and more"})
    assert "Harry Potter = Гарри Поттер, PERSON" in block
    assert "Mordor" not in block


def test_block_empty_without_matches():
    assert utils.build_metadata_vocab_block([], {"title": "x"}) == ""
    assert utils.build_metadata_vocab_block([{"source": "A", "target": "Б"}], {"title": "zzz"}) == ""


def test_translate_metadata_passes_vocab_to_prompt():
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return json.dumps({"title": "Гарри Поттер"})

    with patch.object(utils.llm_service_compat, "get_completion", side_effect=fake):
        utils.translate_metadata({"title": "Harry Potter"}, "english", "russian", "Russia",
                                 vocab_entries=[{"source": "Harry Potter", "target": "Гарри Поттер"}])
    assert "Harry Potter = Гарри Поттер" in captured["vocabulary_block"]
    template = utils.config.prompts["metadata_translation"]["user"]
    assert "{vocabulary_block}" in template
