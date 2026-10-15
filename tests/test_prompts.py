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
INITIAL = dict(source_lang="english", target_lang="russian", country="Россия", outline_text="SYN",
               vocab_dict="Jain = Джайны", characters="Вашти — она (сказала)", source_text="SRC")
CALLS = {
    ("initial_translation", "system"): {},
    ("initial_translation_json", "system"): {},
    ("synopsis", "system"): {},
    ("synopsis", "dictionary_rules"): {},
    **{(cat, "system"): TR for cat in ("reflection", "improve", "editor",
                                        "reflection_json", "improve_json", "editor_json")},
    **{("initial_translation", k): INITIAL for k in ("user_xml", "user_text", "user_hunyuan")},
    **{("reflection", k): dict(LANGS, source_text="SRC", translation="TR", vocab_dict="V",
                               characters="C") for k in ("user_xml", "user_text")},
    **{("improve", k): dict(TR, translation="TR", reflection="R", characters="C")
       for k in ("user_xml", "user_text")},
    **{("editor", k): dict(TR, translation="TR", characters="C") for k in ("user_xml", "user_text")},
    ("gender_fix", "system"): dict(target_lang="russian"),
    ("gender_fix", "user"): dict(characters="C", sentences="1. S", errors="1. E"),
    **{(cat, "user_text"): dict(json_input='{"x": 1}')
       for cat in ("initial_translation_json", "reflection_json", "improve_json", "editor_json")},
    **{("synopsis", k): dict(target_lang="russian", source_text="S", final_translation="T",
                             characters_block="", glossary_block="", dictionary_rules="R")
       for k in ("user",)},
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


# --- the prompts as one pipeline (review of 2026-10) ---------------------------

def test_every_prompt_key_the_code_asks_for_exists():
    """A key missing from prompts.json leaves the model an empty prompt
    (translate_metadata asked for metadata_translation.user_hunyuan)."""
    src = os.path.join(os.path.dirname(__file__), '..', 'src')
    text = "\n".join(open(os.path.join(src, f), encoding='utf-8').read()
                     for f in os.listdir(src) if f.endswith('.py'))
    pairs = set(re.findall(r'get_prompt\(\s*"(\w+)",\s*"(\w+)"', text))
    pairs |= set(re.findall(r'prompt_category="(\w+)",\s*prompt_key="(\w+)"', text))
    assert pairs, "the patterns no longer match the call sites"
    for category, key in pairs:
        assert key in config.prompts.get(category, {}), f"{category}.{key}"


def test_every_stage_that_shapes_the_text_knows_the_readers_country():
    for key in ("user_xml", "user_text", "user_hunyuan"):
        assert "for readers in Россия" in config.get_prompt("initial_translation", key, **INITIAL), key
    for category in ("reflection", "editor", "reflection_json", "editor_json"):
        assert "Россия" in config.get_prompt(category, "system", **TR), category
    assert '"country"' in config.get_prompt("initial_translation_json", "system")


# The rules a stage must carry in both its text and its JSON variant: the two
# drifted apart before (the JSON translator did not know about the terms
# already replaced in the source)
SAME_RULES = {
    "initial_translation": ("profanity", "placeholder", "base form", "omit nothing", "add nothing",
                            "characters", "synopsis"),
    "reflection": ("gender", "profanity", "Replace «X» with «Y»", "never quot"),
    "improve": ("grammar", "markup", "gender", "nothing else"),
    "editor": ("names and acronyms", "profanity", "placeholder", "rewrite correct sentences",
               "add", "gender"),
}


def _whole(category, json_mode):
    name = category + ("_json" if json_mode else "")
    return " ".join(config.prompts[name].values())


def test_text_and_json_variants_carry_the_same_rules():
    for category, rules in SAME_RULES.items():
        for json_mode in (False, True):
            whole = _whole(category, json_mode)
            for rule in rules:
                assert rule in whole, f"{category}{'_json' if json_mode else ''}: {rule!r}"


def test_the_gender_rule_is_in_every_stage_that_writes_text():
    for category in ("initial_translation", "reflection", "improve", "editor",
                     "initial_translation_json", "reflection_json", "improve_json", "editor_json",
                     "gender_fix", "synopsis"):
        whole = " ".join(config.prompts[category].values())
        assert "characters" in whole and "gender" in whole, category


# Prompts are written for models up to 20B: a new rule replaces an old one.
# Raise a budget only on purpose, with prompt_eval.py run on the real models.
BUDGET = {
    ("initial_translation", "system"): 600, ("initial_translation", "user_xml"): 700,
    ("initial_translation", "user_text"): 700, ("initial_translation", "user_hunyuan"): 400,
    ("reflection", "system"): 750, ("improve", "system"): 650, ("editor", "system"): 650,
    ("synopsis", "user"): 450, ("synopsis", "dictionary_rules"): 1400,
    ("initial_translation_json", "system"): 700, ("reflection_json", "system"): 650,
    ("improve_json", "system"): 550, ("editor_json", "system"): 500,
    ("gender_fix", "user"): 400, ("vocabulary", "user"): 720,
}


def test_prompts_stay_within_their_budget():
    for (category, key), budget in BUDGET.items():
        length = len(config.prompts[category][key])
        assert length <= budget, f"{category}.{key}: {length} > {budget}"
