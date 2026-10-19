"""
app.py audit / eval (src/translation_audit.py, src/prompt_eval.py): the measurement of a
translation (mixed alphabets, gender of the characters) before and after a
change of prompts or models. prompt_eval runs with a faked LLM here.
"""
import json
import os
import sys

import pytest
from spacy.util import is_package

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import prompt_eval, translation_audit

needs_ru = pytest.mark.skipif(not is_package("ru_core_news_sm"), reason="ru_core_news_sm not installed")

DIC = "Vashti = Вашти, PERSON, she, \nKuno = Куно, PERSON, , \nMachine = Машина, TERM, , \n"


@needs_ru
def test_audit_counts_mixed_words_gender_errors_and_missing_genders(tmp_path):
    book = tmp_path / "book_ru.txt"
    book.write_text("<p>Вашти сказал, что dошло до Gорода.</p>\n<p>Куно спал. centralные</p>\n",
                    encoding="utf-8")
    dic = tmp_path / "book_ru.dic"
    dic.write_text(DIC, encoding="utf-8")
    report = translation_audit.audit(book, dic, "russian", samples=5)
    assert report["mixed_words"] == 3
    assert {w for w, _ in report["mixed_top"]} == {"dошло", "Gорода", "centralные"}
    assert report["gender_issues"] == 1 and report["gender_samples"][0]["words"] == ["сказал"]
    assert report["persons_without_gender"] == ["Kuno"]


@needs_ru
def test_prompt_eval_runs_the_pipeline_on_the_chosen_passages(tmp_path, monkeypatch):
    import src.utils as u
    book = tmp_path / "book.txt"
    book.write_text("The weather was fine and nobody came.\n\n" * 3
                    + "Vashti said that she was tired. She slept.\n\n", encoding="utf-8")
    dic = tmp_path / "book_ru.dic"
    dic.write_text(DIC, encoding="utf-8")

    def fake_complete(role, system_prompt, user_prompt, max_tokens=0, stage=None, **kw):
        if stage == u.TranslationStage.GENDER:
            return "1. Вашти сказала, что устала.", 5
        return "<ttext>Вашти сказал, что устала. Она уснула.</ttext>", 5

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u.config, 'json_mode', False)
    monkeypatch.setattr(u.config, 'fast_trans', True)
    monkeypatch.setattr(u.config, 'gender_check', 'fix')
    monkeypatch.setattr(u.config, 'source_lang', 'english')
    monkeypatch.setattr(u.config, 'target_lang', 'russian')
    monkeypatch.setattr(u, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    out = tmp_path / "eval" / "run.json"
    prompt_eval.main([str(book), "--dic", str(dic), "--count", "1", "--size", "60", "--out", str(out)])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert "Vashti" in result["source"]
    assert result["translation"] == "Вашти сказала, что устала. Она уснула."
    assert data["summary"]["gender_issues_left"] == 0
    assert out.with_suffix(".md").exists()


@needs_ru
def test_prompt_eval_variants_change_only_this_run(tmp_path, monkeypatch):
    """--prompts / --no-glossary / --no-substitution: the A/B switches that
    look for the cause of a regression (words in two alphabets)."""
    import src.utils as u
    book = tmp_path / "book.txt"
    book.write_text("Vashti met Kuno in the Machine. She was tired.\n\n", encoding="utf-8")
    dic = tmp_path / "book_ru.dic"
    dic.write_text(DIC, encoding="utf-8")
    old_prompts = tmp_path / "old.json"
    # the old reflection.system needed {source_lang}, which the code no longer passes
    old_prompts.write_text('{"initial_translation": {"user_text": "OLD {source_text}", '
                           '"system": "OLD {source_lang}"}}', encoding="utf-8")
    prompts = []

    def fake_complete(role, system_prompt, user_prompt, max_tokens=0, stage=None, **kw):
        prompts.append((stage, user_prompt))
        return "<ttext>Вашти встретила Куно. Она устала.</ttext>", 5

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    for name, value in (('json_mode', False), ('fast_trans', True), ('gender_check', 'off'),
                        ('source_lang', 'english'), ('target_lang', 'russian')):
        monkeypatch.setattr(u.config, name, value)
    monkeypatch.setattr(u, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    monkeypatch.setattr(u.config, 'prompts', {k: dict(v) if isinstance(v, dict) else v
                                              for k, v in u.config.prompts.items()})
    for name in ('_format_vocab_for_prompt', 'replace_vocab_in_text'):
        monkeypatch.setattr(u, name, getattr(u, name))  # restored after the test
    monkeypatch.setattr(u.config, 'get_prompt', u.config.get_prompt)

    def run(*flags):
        prompts.clear()
        out = tmp_path / f"run{len(flags)}.json"
        prompt_eval.main([str(book), "--dic", str(dic), "--count", "1", "--size", "40", "--out", str(out), *flags])
        return next(p for s, p in prompts if s == u.TranslationStage.INITIAL), json.loads(
            out.read_text(encoding="utf-8"))["summary"]

    prompt, summary = run()
    # names are put into the source, an ordinary word ("Machine") stays for the glossary
    assert "Machine = Машина" in prompt and "Вашти met Куно in the Machine" in prompt.split("<source")[1]
    assert summary["variant"] == {'prompts': None, 'prompts_skipped': [], 'no_glossary': False,
                                  'no_substitution': False}
    prompt, summary = run("--no-glossary", "--no-substitution")
    assert "Machine = Машина" not in prompt and "Vashti met Kuno in the Machine" in prompt
    assert summary["variant"]["no_glossary"] and summary["variant"]["no_substitution"]
    prompt, summary = run("--prompts", str(old_prompts))
    assert prompt.startswith("OLD ")
    assert summary["variant"]["prompts_skipped"] == ["initial_translation.system"]

    monkeypatch.setattr(u.config, 'json_mode', True)
    with pytest.raises(SystemExit, match="JSON_MODE=false"):
        run("--no-glossary")


@needs_ru
def test_a_failing_passage_does_not_lose_the_others(tmp_path, monkeypatch):
    import src.utils as u
    book = tmp_path / "book.txt"
    book.write_text("\n\n".join(f"Vashti spoke to Kuno, part {n}. She was tired." for n in range(3)), encoding="utf-8")
    dic = tmp_path / "book_ru.dic"
    dic.write_text(DIC, encoding="utf-8")
    calls = []

    def fake_translate_chunk(**kw):
        calls.append(kw['source_text'])
        if len(calls) == 2:
            raise RuntimeError("API down")
        return "Вашти устала.", ""

    monkeypatch.setattr(u, 'translate_chunk', fake_translate_chunk)
    out = tmp_path / "run.json"
    prompt_eval.main([str(book), "--dic", str(dic), "--count", "3", "--size", "30", "--out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 2 and len(data["failed"]) == 1
    assert "API down" in data["failed"][0]["error"]
