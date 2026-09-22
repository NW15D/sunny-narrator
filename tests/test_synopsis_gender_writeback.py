"""Genders reported by the synopsis stage are written back into the .dic."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as u
from src.vocabulary_manager import apply_character_genders, VocabularyManager

SOURCE = "김철수는 이영희를 만났다. 박민수도 왔다."


def test_extract_genders_strips_block_and_keeps_only_names_in_source():
    response = (
        "Ким Чхольсу встретил Ли Ёнхи.\n\n"
        "<genders>\n"
        "김철수 | Ким Чхольсу | he\n"
        "이영희 | Ли Ёнхи | She\n"
        "홍길동 | Хон Гильдон | he\n"          # not in source: hallucinated
        "박민수 | Пак Минсу | male\n"           # invalid gender value
        "김철수 | Ким Чхольсу | he\n"          # duplicate
        "</genders>"
    )
    synopsis, chars = u.extract_synopsis_genders(response, SOURCE)
    assert synopsis == "Ким Чхольсу встретил Ли Ёнхи."
    assert chars == [
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'she'},
    ]


def test_extract_genders_without_block_returns_text_unchanged():
    assert u.extract_synopsis_genders("Просто синопсис.", SOURCE) == ("Просто синопсис.", [])


def test_generate_synopsis_passes_source_and_reports_characters(monkeypatch):
    seen = {}

    def fake_complete(role, system_prompt, user_prompt, **kw):
        seen['prompt'] = user_prompt
        return "Ким Чхольсу пришёл домой.\n<genders>\n김철수 | Ким Чхольсу | he\n</genders>", 10

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    ctx = u.TranslationContext(
        source_lang='korean', target_lang='russian', source_text=SOURCE,
        outline_text='', vocab_dict={}, vocab_entries=[], country='', style='text'
    )
    result = u.TranslationPipeline().generate_synopsis(ctx, "Ким Чхольсу пришёл домой. " * 20)

    assert SOURCE in seen['prompt']
    assert result.text == "Ким Чхольсу пришёл домой."
    assert result.metadata['characters'] == [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'}]


def test_translate_chunk_fills_character_sink(monkeypatch):
    def fake_execute(**kw):
        state = u.PipelineState(context=None)
        state.add_result(u.TranslationResult(
            stage=u.TranslationStage.SYNOPSIS, llm_role=u.LLMRole.TRANSLATE, text='syn',
            metadata={'characters': [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'}]}
        ))
        state.add_result(u.TranslationResult(
            stage=u.TranslationStage.FINAL, llm_role=u.LLMRole.TRANSLATE, text=SOURCE
        ))
        return state

    monkeypatch.setattr(u._pipeline, 'execute', fake_execute)
    sink = []
    u.translate_chunk('korean', 'russian', SOURCE, '', {}, [], character_sink=sink)
    assert sink == [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'}]


def _write(tmp_path, body):
    path = tmp_path / "book.dic"
    path.write_text("# Vocabulary\n# Format: source = target, category, gender, notes\n\n" + body, encoding='utf-8')
    return str(path)


def test_apply_fills_empty_gender_keeps_existing_and_appends_new(tmp_path):
    dic = _write(tmp_path,
                 "김철수 = Ким Чхольсу, PERSON, , \n"
                 "이영희 = Ли Ёнхи, PERSON, she, героиня\n"
                 "서울 = Сеул, LOC, , \n")
    chars = [
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'he'},      # user's value wins
        {'source': '박민수', 'target': 'Пак, Минсу', 'gender': 'he'},   # new, comma in target
        {'source': '박민수', 'target': 'Пак, Минсу', 'gender': 'he'},   # appended once
    ]
    assert apply_character_genders(dic, chars) == (1, 1)

    lines = open(dic, encoding='utf-8').read().splitlines()
    assert lines[0] == "# Vocabulary"
    assert "김철수 = Ким Чхольсу, PERSON, he, " in lines
    assert "이영희 = Ли Ёнхи, PERSON, she, героиня" in lines
    assert "서울 = Сеул, LOC, , " in lines
    assert lines[-1] == '박민수 = "Пак, Минсу", PERSON, he, '

    # A second pass changes nothing
    assert apply_character_genders(dic, chars) == (0, 0)


def test_apply_matches_by_target_and_sets_category(tmp_path):
    dic = _write(tmp_path, "철수 = Чхольсу, , , \n")
    assert apply_character_genders(dic, [{'source': '김철수', 'target': 'Чхольсу', 'gender': 'he'}]) == (1, 0)
    assert "철수 = Чхольсу, PERSON, he, " in open(dic, encoding='utf-8').read()


def test_vocabulary_manager_reloads_after_recording(tmp_path):
    book = tmp_path / "book.txt"
    book.write_text(SOURCE, encoding='utf-8')
    _write(tmp_path, "김철수 = Ким Чхольсу, PERSON, , \n")
    vm = VocabularyManager(str(book))
    vm.vocab = vm._load_from_file()

    vm.record_character_genders([
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'she'},
    ])

    assert vm.vocab['김철수'].gender == 'he'
    assert vm.vocab['이영희'].target == 'Ли Ёнхи'
    assert vm.vocab['이영희'].category == 'PERSON'
    assert vm.vocab['이영희'].gender == 'she'
