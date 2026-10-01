"""Genders reported by the synopsis stage are written back into the .dic."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as u
from src.vocabulary_manager import apply_dictionary_candidates, VocabularyManager

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
    synopsis, chars = u.extract_dictionary_candidates(response, SOURCE)
    assert synopsis == "Ким Чхольсу встретил Ли Ёнхи."
    assert chars == [
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'she', 'category': 'PERSON'},
    ]


def test_extract_genders_without_block_returns_text_unchanged():
    assert u.extract_dictionary_candidates("Просто синопсис.", SOURCE) == ("Просто синопсис.", [])


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
    assert result.metadata['dictionary_candidates'] == [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'}]


def test_translate_chunk_fills_candidate_sink(monkeypatch):
    def fake_execute(**kw):
        state = u.PipelineState(context=None)
        state.add_result(u.TranslationResult(
            stage=u.TranslationStage.SYNOPSIS, llm_role=u.LLMRole.TRANSLATE, text='syn',
            metadata={'dictionary_candidates': [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'}]}
        ))
        state.add_result(u.TranslationResult(
            stage=u.TranslationStage.FINAL, llm_role=u.LLMRole.TRANSLATE, text=SOURCE
        ))
        return state

    monkeypatch.setattr(u._pipeline, 'execute', fake_execute)
    sink = []
    u.translate_chunk('korean', 'russian', SOURCE, '', {}, [], candidate_sink=sink)
    assert sink == [{'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'}]


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
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'he', 'category': 'PERSON'},      # user's value wins
        {'source': '박민수', 'target': 'Пак, Минсу', 'gender': 'he', 'category': 'PERSON'},   # new, comma in target
        {'source': '박민수', 'target': 'Пак, Минсу', 'gender': 'he', 'category': 'PERSON'},   # appended once
    ]
    assert apply_dictionary_candidates(dic, chars) == (1, 1)

    lines = open(dic, encoding='utf-8').read().splitlines()
    assert lines[0] == "# Vocabulary"
    assert "김철수 = Ким Чхольсу, PERSON, he, " in lines
    assert "이영희 = Ли Ёнхи, PERSON, she, героиня" in lines
    assert "서울 = Сеул, LOC, , " in lines
    assert lines[-1] == '박민수 = "Пак, Минсу", PERSON, he, '

    # A second pass changes nothing
    assert apply_dictionary_candidates(dic, chars) == (0, 0)


def test_apply_matches_by_target_and_sets_category(tmp_path):
    dic = _write(tmp_path, "철수 = Чхольсу, , , \n")
    assert apply_dictionary_candidates(dic, [{'source': '김철수', 'target': 'Чхольсу', 'gender': 'he', 'category': 'PERSON'}]) == (1, 0)
    assert "철수 = Чхольсу, PERSON, he, " in open(dic, encoding='utf-8').read()


def test_vocabulary_manager_reloads_after_recording(tmp_path):
    book = tmp_path / "book.txt"
    book.write_text(SOURCE, encoding='utf-8')
    _write(tmp_path, "김철수 = Ким Чхольсу, PERSON, , \n")
    vm = VocabularyManager(str(book))
    vm.vocab = vm._load_from_file()

    vm.record_dictionary_candidates([
        {'source': '김철수', 'target': 'Ким Чхольсу', 'gender': 'he', 'category': 'PERSON'},
        {'source': '이영희', 'target': 'Ли Ёнхи', 'gender': 'she'},
    ])

    assert vm.vocab['김철수'].gender == 'he'
    assert vm.vocab['이영희'].target == 'Ли Ёнхи'
    assert vm.vocab['이영희'].category == 'PERSON'
    assert vm.vocab['이영희'].gender == 'she'


def test_common_nouns_are_not_added_to_dictionary(tmp_path):
    from src.vocabulary_manager import apply_dictionary_candidates, looks_like_proper_name

    assert looks_like_proper_name("Ares") and looks_like_proper_name("Runcible AI")
    assert looks_like_proper_name("Ludwig von Mises") and looks_like_proper_name("김철수")
    assert not looks_like_proper_name("Jain soldier")
    assert not looks_like_proper_name("submind") and not looks_like_proper_name("worm fragment")

    dic = tmp_path / "b.dic"
    dic.write_text("Ares = Арес, PERSON, , \n", encoding="utf-8")
    chars = [
        {'source': 'Jain soldier', 'target': 'солдат Джайнов', 'gender': 'he', 'category': 'PERSON'},
        {'source': 'submind', 'target': 'субразум', 'gender': 'it'},
        {'source': 'Ares', 'target': 'Арес', 'gender': 'he', 'category': 'PERSON'},
        {'source': 'Orlandine', 'target': 'Орландина', 'gender': 'she'},
    ]
    assert apply_dictionary_candidates(str(dic), chars) == (1, 1)
    text = dic.read_text(encoding="utf-8")
    assert "Orlandine" in text and "soldier" not in text and "submind" not in text


def test_coined_terms_block_is_extracted_and_written(tmp_path):
    from src.vocabulary_manager import apply_dictionary_candidates

    source = "Ares fired the spidergun. The gubbleduck ran, and then the end came."
    response = (
        "Арес выстрелил.\n"
        "<genders>\nAres | Арес | he\n</genders>\n"
        "<terms>\nspidergun | паукопушка\ngubbleduck | губбльутка\n"
        "then | потом\nend | конец\nAres | Арес\nghost | призрак\n</terms>"
    )
    synopsis, chars = u.extract_dictionary_candidates(response, source, "english")
    assert synopsis == "Арес выстрелил."
    # stop word, short word and a term absent from the source are dropped
    assert [(c['source'], c['category']) for c in chars] == [
        ('Ares', 'PERSON'), ('spidergun', 'TERM'), ('gubbleduck', 'TERM')]

    dic = tmp_path / "b.dic"
    dic.write_text("spidergun = паукострел, TERM, , \n", encoding="utf-8")
    assert apply_dictionary_candidates(str(dic), chars) == (0, 2)
    text = dic.read_text(encoding="utf-8")
    assert "паукострел" in text and "паукопушка" not in text  # existing line wins
    assert "gubbleduck = губбльутка, TERM, , " in text
    assert "Ares = Арес, PERSON, he, " in text


def test_terms_survive_missing_closing_genders_tag():
    response = ("Синопсис.\n<genders>\nAres | Арес | he\n"
                "<terms>\nspidergun | паукопушка\n</terms>")
    synopsis, chars = u.extract_dictionary_candidates(response, "Ares and the spidergun.", "english")
    assert synopsis == "Синопсис."
    assert [(c['source'], c['category']) for c in chars] == [('Ares', 'PERSON'), ('spidergun', 'TERM')]


def test_cjk_terms_are_not_cut_by_the_length_minimum():
    response = "Синопсис.\n<terms>\n거미총 | паукопушка\n</terms>"
    _, chars = u.extract_dictionary_candidates(response, "철수는 거미총을 들었다.", "korean")
    assert [c['source'] for c in chars] == ['거미총']


def test_term_in_base_form_matches_inflected_source_and_ignores_markup():
    # the source only has the plural; tag and attribute names are not terms
    source = '<p>The <emphasis>spiderguns</emphasis> fired.</p><image href="#x"/>'
    response = "С.\n<terms>\nspidergun | паукопушка\nemphasis | выделение\nhref | ссылка\n</terms>"
    _, chars = u.extract_dictionary_candidates(response, source, "english")
    assert [c['source'] for c in chars] == ['spidergun']


def test_term_with_a_shared_translation_is_still_added(tmp_path):
    dic = tmp_path / "b.dic"
    dic.write_text("duck = утка, TERM, , \n", encoding="utf-8")
    assert apply_dictionary_candidates(
        str(dic), [{'source': 'gubbleduck', 'target': 'утка', 'gender': '', 'category': 'TERM'}]) == (0, 1)
    assert "gubbleduck = утка, TERM, , " in dic.read_text(encoding="utf-8")


def test_gender_report_upgrades_a_term_to_person(tmp_path):
    dic = tmp_path / "b.dic"
    dic.write_text("Orlandine = Орландина, TERM, , \n", encoding="utf-8")
    assert apply_dictionary_candidates(
        str(dic), [{'source': 'Orlandine', 'target': 'Орландина', 'gender': 'she', 'category': 'PERSON'}]) == (1, 0)
    assert "Orlandine = Орландина, PERSON, she, " in dic.read_text(encoding="utf-8")


def test_dictionary_rules_are_shared_by_both_prompts_and_ask_for_base_form():
    rules = u.config.get_prompt("synopsis", "dictionary_rules")
    assert "<terms>" in rules and "nominative case" in rules
    for key in ("user", "user_hunyuan"):
        prompt = u.config.get_prompt("synopsis", key, target_lang="russian", source_text="s",
                                     final_translation="t", characters_block="",
                                     dictionary_rules=rules)
        assert prompt.endswith(rules)
