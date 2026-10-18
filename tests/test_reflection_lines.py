"""Text-mode reflection: lines whose X is not in the translation are dropped
(the improve stage cannot apply them), like the JSON fixes."""
from src.utils import _keep_applicable_lines

TR = "Мара открыл дверь. Тобиас ждала в коридоре."


def test_keeps_applicable_lines_with_and_without_guillemets():
    text = "Мара открыл → Мара открыла — род\\n«ждала» → «ждал» — род"
    assert _keep_applicable_lines(text.replace("\\n", "\n"), TR, "russian").count("→") == 2


def test_drops_absent_find_and_noop_lines():
    text = "Мара открыла → Мара открыла дверь — нет такого\nждала → ждала — ничего\nждала → ждал — род"
    assert _keep_applicable_lines(text, TR, "russian") == "ждала → ждал — род"


def test_no_changes_when_every_line_is_dropped():
    assert _keep_applicable_lines("нет такого → есть — причина", TR, "russian") == "NO CHANGES"


def test_other_shapes_pass_through():
    assert _keep_applicable_lines("NO CHANGES", TR, "russian") == "NO CHANGES"
    assert _keep_applicable_lines("общее замечание", TR, "russian") == "общее замечание"


def test_list_markers_and_bold_are_not_part_of_the_find():
    text = "- «Мара открыл» → «Мара открыла» — род\n* **«ждала»** → **«ждал»** — род"
    kept = _keep_applicable_lines(text, TR, "russian")
    assert kept.count("→") == 2 and "NO CHANGES" not in kept


def test_json_fixes_without_find_do_not_crash():
    from src.utils import _keep_applicable_fixes
    raw = '[{"wrong": "a", "right": "b"}, {"find": "ждала", "replace": "ждал", "reason": "род"}]'
    assert '"find": "ждала"' in _keep_applicable_fixes(raw, TR, "russian")
    assert _keep_applicable_fixes('[{"find": "ждала", "replace": "ждала"}]', TR, "russian") == ""


# --- the vocabulary is kept by the code (a novel, 2026-10-17) -------------
# Asked to check the terms, the reviewer listed every one as a fix that
# changes nothing, twice over, until max_tokens; it no longer checks them, so
# a fix that takes a dictionary translation out of the text is dropped here.

TERMS = ["Трик", "ЮЗЕР", "Государство"]
TR_TERMS = "Трик ждал. Помехи ЮЗЕРа росли. Флот Государства ушёл."


def test_a_fix_that_replaces_a_term_is_dropped():
    from src.utils import _keep_applicable_fixes
    raw = ('[{"find": "Трик ждал", "replace": "Трайк ждал", "reason": "имя"},'
           ' {"find": "Помехи ЮЗЕРа", "replace": "Помехи USER", "reason": "термин"}]')
    assert _keep_applicable_fixes(raw, TR_TERMS, "russian", TERMS) == ""


def test_a_fix_that_inflects_a_term_or_leaves_it_is_kept():
    from src.utils import _keep_applicable_fixes
    raw = ('[{"find": "Флот Государства ушёл", "replace": "Флот Государства улетел", "reason": "смысл"},'
           ' {"find": "Трик ждал", "replace": "Трика ждали", "reason": "согласование"}]')
    kept = _keep_applicable_fixes(raw, TR_TERMS, "russian", TERMS)
    assert "улетел" in kept and "Трика ждали" in kept


def test_text_mode_drops_a_line_that_replaces_a_term():
    text = "Трик ждал → Трайк ждал — имя\nТрик ждал → Трик ждала — род"
    assert _keep_applicable_lines(text, TR_TERMS, "russian", TERMS) == "Трик ждал → Трик ждала — род"


def test_a_fix_with_a_source_language_word_is_dropped():
    # IMPROVE given one such fix applied none of the 13 fixes of the chunk
    from src.utils import _keep_applicable_fixes
    raw = ('[{"find": "Флот Государства ушёл", "replace": "Флот Государства black-ops ушёл", "reason": "смысл"},'
           ' {"find": "Трик ждал", "replace": "Трика ждали", "reason": "согласование"}]')
    kept = _keep_applicable_fixes(raw, TR_TERMS, "russian", TERMS)
    assert "black-ops" not in kept and "Трика ждали" in kept


def test_a_dictionary_translation_in_latin_letters_is_not_foreign():
    from src.utils import _keep_applicable_fixes
    tr = "Ракета SpaceX взлетела."
    raw = '[{"find": "Ракета SpaceX взлетела", "replace": "Ракета SpaceX стартовала", "reason": "смысл"}]'
    assert "стартовала" in _keep_applicable_fixes(raw, tr, "russian", ["SpaceX"])
