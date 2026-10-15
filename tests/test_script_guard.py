"""
Words of a translation written in two alphabets ("dошло", "Gород"): a small
model starts the word with the Latin letter of the same sound or shape.
script_guard puts them back into the target alphabet without an LLM.
The words below come from a real Russian translation of the demo book.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import script_guard as sg


@pytest.mark.parametrize("word, fixed", [
    ("dошло", "дошло"), ("Gород", "Город"), ("dети", "дети"), ("gолосом", "голосом"),
    ("tьма", "тьма"), ("taкого", "такого"),        # two Latin letters
    ("eё", "её"), ("eго", "его"),                  # "эго" is a word too: the shape wins
    ("cелый", "целый"),                            # "селый" is no word: the sound wins
    ("mиссии", "миссии"), ("nи", "ни"),
])
def test_russian_words_from_a_real_translation(word, fixed):
    text, fixes, unfixed = sg.fix_mixed_script(f"Он сказал: {word}.", "russian")
    assert text == f"Он сказал: {fixed}." and fixes == [(word, fixed)] and unfixed == []


def test_an_ambiguous_or_unknown_word_is_reported_not_guessed():
    # "центральные" has a soft sign that "central" has not; "cениете" is no word either way
    text, fixes, unfixed = sg.fix_mixed_script("centralные части, cениете", "ru")
    assert text == "centralные части, cениете" and fixes == []
    assert unfixed == ["centralные", "cениете"]


def test_a_name_inflected_from_the_dictionary_is_fixed():
    # "Ворту" is not in the word list, but shares its stem with "Ворта"
    text, fixes, _ = sg.fix_mixed_script("Они пошли к Вортy.", "ru", ["Ворта"])
    assert text == "Они пошли к Ворту."


def test_markup_latin_words_and_dictionary_targets_are_left_alone():
    source = ('<p>Он купил <a l:href="#n1">iPhone</a> и eBook-ридер ![](sn-imgref-3), '
              'см. https://example.com/дом</p>')
    text, fixes, unfixed = sg.fix_mixed_script(source, "ru", ["eBook-ридер"])
    assert text == source and fixes == [] and unfixed == []


def test_find_mixed_words_skips_markup():
    assert sg.find_mixed_words('<p class="x">Gород</p> [](sn-htmlref-2)', "ru") == ["Gород"]
    assert sg.find_mixed_words("Город и Paris", "ru") == []


def test_latin_target_gets_cyrillic_letters_out():
    # a translation from Russian: Cyrillic "ѕ" and "е" inside French words
    text, fixes, _ = sg.fix_mixed_script("Il était trèѕ fatiguе.", "french")
    assert text == "Il était très fatigue."
    assert fixes == [("trèѕ", "très"), ("fatiguе", "fatigue")]


def test_a_word_seen_elsewhere_in_the_text_decides_without_a_word_list():
    # no pymorphy3 dictionary for Bulgarian: "c" -> "с" or "ц" is decided by
    # the same word written correctly elsewhere in the chunk
    text, fixes, _ = sg.fix_mixed_script("Той е цял ден тук. Беше cял ден там.", "bg")
    assert "Беше цял ден" in text


def test_languages_in_other_scripts_are_not_checked():
    assert sg.fix_mixed_script("他说dошло", "chinese") == ("他说dошло", [], [])
    assert sg.target_script("japanese") is None
    assert sg.target_script("ukrainian") == "CYRILLIC" and sg.target_script("greek") == "GREEK"


def test_the_alphabet_of_the_language_limits_the_candidates():
    # Ukrainian has "і" and "ґ", Russian has not
    assert sg.fix_mixed_script("Вiн пішов.", "uk")[0] == "Він пішов."
    assert "і" not in sg.fix_mixed_script("Вiн пошёл.", "ru")[0]


def test_greek_notation_in_a_latin_text_is_left_alone():
    source = "Une cellule de 5 μm et 3 μg de Δx, la constante λmax."
    assert sg.fix_mixed_script(source, "french") == (source, [], [])
    assert sg.find_mixed_words(source, "french") == []


def test_report_and_fix_protect_the_same_dictionary_words():
    text = "Звезда Proxима сияла."
    assert sg.find_mixed_words(text, "ru", ["Proxима Центавра"]) == []
    assert sg.fix_mixed_script(text, "ru", ["proxима центавра"]) == (text, [], [])
    assert sg.find_mixed_words(text, "ru") == ["Proxима"]
