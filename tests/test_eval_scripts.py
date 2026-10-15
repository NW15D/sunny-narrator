"""
scripts/translation_audit.py and scripts/prompt_eval.py: the measurement of a
translation (mixed alphabets, gender of the characters) before and after a
change of prompts or models. prompt_eval runs with a faked LLM here.
"""
import json
import os
import sys

import pytest
from spacy.util import is_package

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts import prompt_eval, translation_audit

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
    assert report["mixed_words"] == 3 and report["mixed_fixable"] == 2
    assert report["unfixable"] == ["centralные"]
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
    monkeypatch.setattr(sys, 'argv', ["prompt_eval.py", str(book), "--dic", str(dic),
                                      "--count", "1", "--size", "60", "--out", str(out)])
    prompt_eval.main()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert "Vashti" in result["source"]
    assert result["translation"] == "Вашти сказала, что устала. Она уснула."
    assert data["summary"]["gender_issues_left"] == 0
    assert out.with_suffix(".md").exists()
