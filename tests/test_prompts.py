"""
Every prompt template formats completely with exactly the variables its call
site passes (src/utils.py). A missing variable is silent in production:
get_prompt returns the raw template, and the model reads "{target_lang}"
literally — reflection.system did so with {source_lang}, which its caller
never passed.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import Config

config = Config()

TR = dict(target_lang="russian", country="Россия")
LANGS = dict(source_lang="english", target_lang="russian", country="Россия")
INITIAL = dict(source_lang="english", target_lang="russian", outline_text="SYN",
               vocab_dict="Jain = Джайны", source_text="SRC")
CALLS = {
    ("initial_translation", "system"): {},
    ("initial_translation_json", "system"): {},
    ("synopsis", "system"): {},
    ("synopsis", "dictionary_rules"): {},
    **{(cat, "system"): TR for cat in ("reflection", "improve", "editor",
                                        "reflection_json", "improve_json", "editor_json")},
    **{("initial_translation", k): INITIAL for k in ("user_xml", "user_text", "user_hunyuan")},
    **{("reflection", k): dict(LANGS, source_text="SRC", translation="TR", vocab_dict="V")
       for k in ("user_xml", "user_text")},
    **{("improve", k): dict(TR, translation="TR", reflection="R", vocab_dict="V")
       for k in ("user_xml", "user_text")},
    **{("editor", k): dict(TR, translation="TR") for k in ("user_xml", "user_text")},
    **{(cat, "user_text"): dict(json_input='{"x": 1}')
       for cat in ("initial_translation_json", "reflection_json", "improve_json", "editor_json")},
    **{("synopsis", k): dict(target_lang="russian", source_text="S", final_translation="T",
                             characters_block="", glossary_block="", dictionary_rules="R")
       for k in ("user", "user_hunyuan")},
    ("vocabulary", "user"): dict(LANGS, source_text="Jain [ORG]"),
    ("metadata_translation", "user"): dict(LANGS, metadata_json="{}", vocabulary_block=""),
    ("image_generation", "generation"): dict(target_lang="russian", title="T", authors_str="A",
                                             genres="G", annotation="N"),
    ("image_generation", "variation"): dict(source_lang="english", target_lang="russian"),
}


def test_every_prompt_formats_with_the_variables_of_its_call_site():
    for (category, key), kwargs in CALLS.items():
        template = config.prompts[category][key]
        out = template.format(**kwargs)  # raises on a missing or stray placeholder
        assert not re.search(r'\{[a-z_]+\}', out), f"{category}.{key}"


def test_no_prompt_is_left_unchecked():
    keys = {(c, k) for c, v in config.prompts.items() if isinstance(v, dict) for k in v}
    assert keys == set(CALLS), "add the new prompt and its call-site variables to CALLS"


def test_translation_prompts_carry_the_glossary_and_keep_markup():
    for key in ("user_xml", "user_text", "user_hunyuan"):
        assert "Jain = Джайны" in config.get_prompt("initial_translation", key, **INITIAL), key
    for category in ("initial_translation", "improve", "editor"):
        system = config.get_prompt(category, "system", **TR)
        assert "XML tag" in system and "placeholder" in system, category
    # the JSON translator must keep FB2 tags, not drop them
    assert "Keep every XML tag" in config.get_prompt("initial_translation_json", "system")


def test_reflection_gives_self_contained_fixes_and_improve_accepts_none():
    system = config.get_prompt("reflection", "system", **TR)
    assert "{" not in system and "NO CHANGES" in system and "russian" in system
    assert "NO CHANGES" in config.get_prompt("improve", "system", **TR)
