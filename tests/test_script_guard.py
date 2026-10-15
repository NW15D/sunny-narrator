"""
Words of a translation written in two alphabets ("dошло", "Gород"): the
model switched alphabets mid-word. script_guard finds them for the log and
the measurement scripts; it never changes the text. The words below come
from real Russian translations of the demo books.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import script_guard as sg


@pytest.mark.parametrize("word", [
    "dошло", "Gород", "dети", "gолосом", "taкого", "eё", "cапитан", "centralные", "Вортy",
])
def test_russian_mixed_words_from_real_translations_are_found(word):
    assert sg.find_mixed_words(f"Он сказал: {word}.", "russian") == [word]


def test_names_acronyms_markup_and_dictionary_words_are_not_mixed():
    source = ('<p>Он купил <a l:href="#n1">iPhone</a> и eBook-ридер ![](sn-imgref-3), '
              'см. https://example.com/дом, NASA и Paris.</p>')
    assert sg.find_mixed_words(source, "ru", ["eBook-ридер"]) == []
    assert sg.find_mixed_words("Звезда Proxима сияла.", "ru", ["Proxима Центавра"]) == []
    assert sg.find_mixed_words("Звезда Proxима сияла.", "ru") == ["Proxима"]
    assert sg.find_mixed_words('<p class="x">Gород</p> [](sn-htmlref-2)', "ru") == ["Gород"]


def test_latin_target_cyrillic_inside_a_word_greek_notation_is_fine():
    assert sg.find_mixed_words("Il était trèѕ fatiguе.", "french") == ["trèѕ", "fatiguе"]
    assert sg.find_mixed_words("Une cellule de 5 μm et 3 μg de Δx, la constante λmax.", "french") == []


def test_other_scripts_are_not_checked():
    assert sg.find_mixed_words("他说dошло", "chinese") == []
    assert sg.target_script("japanese") is None
    assert sg.target_script("ukrainian") == "CYRILLIC" and sg.target_script("greek") == "GREEK"
    assert sg.find_mixed_words("Ο Γιάννης είπε Kαλημέρα.", "el") == ["Kαλημέρα"]
