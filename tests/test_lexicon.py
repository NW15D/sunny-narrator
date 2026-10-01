"""Language-aware glossary matching and stop words (src/lexicon.py).

One matcher serves every input format (FB2/TXT and EPUB/DOCX/PDF), so
these cases pin the behaviour across scripts: inflected forms in
space-separated languages, substring matching for CJK, no matches inside
unrelated words.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import lexicon


def test_plural_matches_base_form():
    assert lexicon.find_terms("Two spiderguns fired.", ["spidergun"], "english") == ["spidergun"]


def test_russian_inflection_matches():
    text = "Он выстрелил из паукопушек, потом взял паукопушку."
    assert lexicon.find_terms(text, ["паукопушка"], "russian") == ["паукопушка"]


def test_term_inside_other_word_does_not_match():
    assert lexicon.find_terms("Annoying noise.", ["Ann"], "english") == []


def test_multi_word_term_needs_consecutive_words():
    assert lexicon.find_terms("The Mad Hatters laughed.", ["Mad Hatter"], "en") == ["Mad Hatter"]
    assert lexicon.find_terms("The mad old hatter.", ["Mad Hatter"], "en") == []


def test_hyphen_and_case_are_normalized():
    assert lexicon.find_terms("SPIDER-GUNS everywhere", ["spider gun"], "en") == ["spider gun"]


def test_lemma_map_covers_irregular_forms():
    # Snowball cannot relate wolves/wolf; a spaCy lemma map can.
    assert lexicon.find_terms("The wolves howled", ["wolf"], "en") == []
    assert lexicon.find_terms("The wolves howled", ["wolf"], "en", {"wolves": {"wolf"}}) == ["wolf"]


def test_cjk_terms_match_as_substrings():
    text = "李雷拿起蜘蛛枪。"
    assert lexicon.find_terms(text, ["蜘蛛枪", "李雷", "韩梅梅"], "chinese") == ["蜘蛛枪", "李雷"]
    assert lexicon.find_terms("ロンはスパイダーガンを持った", ["スパイダーガン"], "ja") == ["スパイダーガン"]


def test_korean_term_with_attached_particle():
    assert lexicon.find_terms("철수는 집에 갔다", ["철수"], "korean") == ["철수"]


def test_fullwidth_latin_is_normalized():
    assert lexicon.find_terms("ＡＢＣ社の製品", ["ABC"], "ja") == ["ABC"]


def test_stop_words_for_non_english_languages():
    assert "и" in lexicon.get_stop_words("russian")
    assert "und" in lexicon.get_stop_words("de")
    # No NLTK list for Polish/Ukrainian/Japanese: spaCy provides it
    assert "się" in lexicon.get_stop_words("polish")
    assert "та" in lexicon.get_stop_words("ukrainian")
    assert "これ" in lexicon.get_stop_words("japanese")
    # English fiction extras stay English-only
    assert "said" in lexicon.get_stop_words("english")
    assert "said" not in lexicon.get_stop_words("russian")


def test_names_ending_in_s_do_not_match_common_words():
    # stem("Ares") == "are", "Wells" -> "well": a stop-word stem must not match
    assert lexicon.find_terms("They are here", ["Ares"], "english") == []
    assert lexicon.find_terms("All is well, he went down", ["Wells", "Downs"], "en") == []
    assert lexicon.find_terms("Ares and Wells came", ["Ares", "Wells"], "en") == ["Ares", "Wells"]
