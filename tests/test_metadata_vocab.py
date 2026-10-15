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


def test_synopsis_characters_lists_gender_of_present_characters():
    entries = [
        {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she"},
        {"source": "Bob", "target": "Боб", "category": "PERSON", "gender": "he"},
        {"source": "Rome", "target": "Рим", "category": "LOC", "gender": ""},
    ]
    block = utils.build_synopsis_characters(entries, "Алиса пришла в Рим.", "russian")
    assert "Алиса — она (сказала)" in block
    assert "Боб" not in block and "Рим" not in block
    assert utils.build_synopsis_characters(entries, "Никого нет.") == ""
    assert utils.build_synopsis_characters([], "Алиса") == ""


def test_metadata_prompt_is_not_empty_with_a_hunyuan_translate_model(monkeypatch):
    """translate_metadata asked for metadata_translation.user_hunyuan, a key
    that does not exist: the model got an empty prompt."""
    seen = {}

    def fake_get_completion(role, prompt_category, prompt_key=None, **kw):
        seen['prompt'] = utils.config.get_prompt(prompt_category, prompt_key, **kw)
        return '{"title": "Книга"}'

    monkeypatch.setattr(utils.config, 'model_translate', 'Hunyuan')
    monkeypatch.setattr(utils.llm_service_compat, 'get_completion', fake_get_completion)
    utils.translate_metadata({"title": "Book"}, "english", "russian", "Россия")
    assert "<metadata>" in seen['prompt']
