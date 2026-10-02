"""Priority of multi-word glossary terms and safe substitution into the chunk
(src/term_substitution.py, lexicon.resolve_terms)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import lexicon
from src.term_substitution import replace_vocab_in_text as sub

V = {"Hatter": "Шляпник", "Mad Hatter": "Безумный Шляпник"}


def test_multi_word_term_wins_over_contained_word():
    assert sub("The Mad Hatter came.", V) == "The Безумный Шляпник came."


def test_contained_word_still_replaced_elsewhere():
    assert sub("Mad Hatter met a Hatter.", V) == "Безумный Шляпник met a Шляпник."


def test_longer_multi_word_wins_over_shorter_multi_word():
    v = {"Red Queen": "Красная Королева", "Red Queen's Court": "Двор Красной Королевы"}
    assert sub("The Red Queen's Court", v) == "The Двор Красной Королевы"


def test_priority_is_by_words_not_by_characters():
    v = {"Wonderland": "Страна Чудес", "Wonderland X": "Икс"}
    assert sub("Wonderland X", v) == "Икс"
    v = {"Extraordinarily": "Необычайно", "A B": "АБ"}
    assert sub("A B Extraordinarily", v) == "АБ Необычайно"


def test_shadowed_term_is_not_found():
    found, shadowed = lexicon.resolve_terms("The Mad Hatter came.", list(V), "en")
    assert found == ["Mad Hatter"] and shadowed == ["Hatter"]
    assert lexicon.find_terms("Mad Hatter and a Hatter", list(V), "en") == ["Hatter", "Mad Hatter"]


def test_whitespace_and_apostrophe_variants():
    assert sub("Mad\n  Hatter", V) == "Безумный Шляпник"
    assert sub("Queen’s Court", {"Queen's Court": "Двор Королевы"}) == "Двор Королевы"


def test_markup_is_untouched():
    v = {"title": "заголовок", "spidergun": "паукопушка"}
    assert sub('<title>Spidergun</title><a l:href="#spidergun">spidergun</a>', v) == \
        '<title>Паукопушка</title><a l:href="#spidergun">паукопушка</a>'
    assert sub("a < b spidergun", v) == "a < b паукопушка"


def test_markup_does_not_match_terms():
    assert lexicon.find_terms("<title>Hello</title>", ["title"], "en") == []


def test_no_term_across_markup_in_matching_and_substitution():
    # Two paragraphs are not the phrase; "Hatter" must not be shadowed by it
    for text in ("Mad</p><p>Hatter", "Mad <emphasis>Hatter</emphasis>"):
        assert lexicon.resolve_terms(text, list(V), "en") == (["Hatter"], [])
        assert "Шляпник" in sub(text, V) and "Безумный" not in sub(text, V)


def test_case_variant_does_not_shadow():
    # lexicon finds "mad Hatter" casefolded, substitution rejects it: "Hatter" must survive
    found, shadowed = lexicon.resolve_terms("the mad Hatter came", list(V), "en")
    assert "Hatter" in found and shadowed == []
    assert sub("the mad Hatter came", V) == "the mad Шляпник came"
    # an inflected occurrence in the term's case still shadows
    assert lexicon.resolve_terms("The Mad Hatters came", list(V), "en") == (["Mad Hatter"], ["Hatter"])
    assert lexicon.resolve_terms("THE MAD HATTER", list(V), "en") == (["Mad Hatter"], ["Hatter"])


def test_rank_counts_words_like_lexicon():
    # "Jean-Luc-Marie" is three words for both modules, so it beats "Marie Curie"
    v = {"Jean-Luc-Marie": "Жан-Люк-Мари", "Marie Curie": "Мария Кюри"}
    text = "Jean-Luc-Marie Curie came; Jean-Luc-Marie and Marie Curie."
    assert lexicon.term_rank("Jean-Luc-Marie") == (3, 14)
    assert sub(text, v) == "Жан-Люк-Мари Curie came; Жан-Люк-Мари and Мария Кюри."
    assert lexicon.resolve_terms(text, list(v), "en") == (list(v), [])


def test_escaped_angle_brackets_are_text():
    text = "\\<Skill acquired: Spidergun\\>"
    assert lexicon.find_terms(text, ["spidergun"], "en") == ["spidergun"]
    assert sub(text, {"spidergun": "паукопушка"}) == "\\<Skill acquired: Паукопушка\\>"


def test_markdown_targets_are_untouched():
    v = {"spidergun": "паукопушка"}
    cases = {
        "[Spidergun](https://x.org/spidergun)": "[Паукопушка](https://x.org/spidergun)",
        '[a](<sp ider/spidergun> "spidergun")': '[a](<sp ider/spidergun> "spidergun")',
        "# Spidergun {#spidergun .spidergun}": "# Паукопушка {#spidergun .spidergun}",
        "see <https://x.org/spidergun> or https://x.org/spidergun.": "see <https://x.org/spidergun> or https://x.org/spidergun.",
        "[spidergun]: https://x.org/spidergun": "[spidergun]: https://x.org/spidergun",
        "![](sn-imgref-0) spidergun": "![](sn-imgref-0) паукопушка",
    }
    for text, expected in cases.items():
        assert sub(text, v) == expected
    assert lexicon.find_terms("[a](https://x.org/spidergun)", ["spidergun"], "en") == []


def test_xml_targets_and_sources_are_escaped():
    assert sub("<p>Tom met Jerry</p>", {"Tom": "Б&К"}, xml=True) == "<p>Б&amp;К met Jerry</p>"
    assert sub("<p>AT&amp;T won</p>", {"AT&T": "ЭйТиЭндТи"}, xml=True) == "<p>ЭйТиЭндТи won</p>"
    assert sub("Tom met Jerry", {"Tom": "Б&К"}) == "Б&К met Jerry"


def test_prompt_order_follows_rank():
    terms = ["Gun", "spider-gun", "Big Gun Tower", "Big Gun"]
    assert sorted(terms, key=lexicon.term_rank, reverse=True) == \
        ["Big Gun Tower", "spider-gun", "Big Gun", "Gun"]


def test_case_rules():
    assert sub("Spidergun, SPIDERGUN, spidergun", {"spidergun": "паукопушка"}) == \
        "Паукопушка, ПАУКОПУШКА, паукопушка"
    assert sub("will Will WILL", {"Will": "Уилл"}) == "will Уилл УИЛЛ"


def test_unspaced_script_without_word_boundaries():
    assert sub("彼は魔王城で魔王を倒した", {"魔王": "Маō", "魔王城": "Замок"}) == "彼はЗамокでМаōを倒した"


def test_whole_words_only_and_no_chained_replacement():
    assert sub("dragonfly dragon", {"dragon": "драккар"}) == "dragonfly драккар"
    assert sub("a b", {"a": "b", "b": "c"}) == "b c"


def test_empty_inputs():
    assert sub("", V) == ""
    assert sub("text", {}) == "text"


def test_xml_entities_are_not_terms():
    assert sub("<p>Tom &amp; Jerry &#38; &lt;x&gt;</p>", {"amp": "X", "lt": "Y", "38": "Z"}, xml=True) == \
        "<p>Tom &amp; Jerry &#38; &lt;x&gt;</p>"
    assert sub("<p>amp lt</p>", {"amp": "X", "lt": "Y"}, xml=True) == "<p>X Y</p>"
    assert lexicon.find_terms("<p>Tom &amp; Jerry</p>", ["amp"], "en") == []


def test_status_line_is_not_a_reference_definition():
    v = {"Hatter": "Шляпник"}
    assert sub("[Level]: 5 Hatter", v) == "[Level]: 5 Шляпник"
    assert lexicon.find_terms("[Level]: 5 Hatter", ["Hatter"], "en") == ["Hatter"]
    assert sub("[Hatter]: https://x.org/Hatter", v) == "[Hatter]: https://x.org/Hatter"


def test_latin_term_inside_cjk_text():
    v = {"ABC": "АБС"}
    assert sub("ABC社の製品", v) == "АБС社の製品"
    assert sub("ＡＢＣ社の製品", v) == "АБС社の製品"
    assert sub("ABCD社", v) == "ABCD社"
    assert lexicon.find_terms("ABC社の製品", ["ABC"], "ja") == ["ABC"]


def test_korean_particle_stays_after_replacement():
    assert sub("철수는 집에 갔다", {"철수": "Чхольсу"}) == "Чхольсу는 집에 갔다"


def test_cjk_priority_longest_term_wins():
    v = {"魔王": "Маō", "魔王城": "Замок демона"}
    assert sub("彼は魔王城で魔王を倒した", v) == "彼はЗамок демонаでМаōを倒した"
    assert lexicon.resolve_terms("魔王城", list(v), "ja") == (["魔王城"], ["魔王"])


def test_unspaced_ranges_match_lexicon():
    from src import term_substitution as ts
    pattern = re.compile(f"[{ts._UNSPACED_RANGES}]")
    for ch in "漢字かなカナ한글ｶﾅ์ไทยລາວខ្មែរမြန်မာབོད":
        assert lexicon._is_unspaced_char(ch) == bool(pattern.match(ch)), ch
    for ch in "AzÀж1":
        assert not pattern.match(ch)


def test_cjk_stop_words_are_available():
    assert "的" in lexicon.get_stop_words("chinese")
    assert "は" in lexicon.get_stop_words("japanese")
    assert lexicon.is_stop_word("这", lexicon.get_stop_words("zh"))
