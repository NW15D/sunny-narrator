"""Priority of multi-word glossary terms and safe substitution into the chunk
(src/term_substitution.py, lexicon.resolve_terms)."""
import os
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
    assert lexicon.find_terms("Mad <emphasis>Hatter</emphasis>", ["Mad Hatter"], "en") == ["Mad Hatter"]


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
