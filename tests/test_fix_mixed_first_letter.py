"""
fix_mixed_first_letter: a Latin FIRST letter of an otherwise all-Cyrillic
word ("dирективы") is a keyboard-layout slip and gets the Cyrillic
homoglyph; purely-Latin words (FBI, iPhone) and mid-word slips stay.
The TC-009 prototype tests, pointed at the shipped function.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.script_guard import fix_mixed_first_letter as fix


def test_core_map_lowercase():
    assert fix('dирективы', 'ru') == 'директивы'
    assert fix('tехнологии', 'ru') == 'технологии'
    assert fix('cасанием', 'ru') == 'сасанием'
    assert fix('gоворит', 'ru') == 'говорит'
    assert fix('pодины', 'ru') == 'подины'
    assert fix('eкран', 'ru') == 'экран'
    assert fix('yтро', 'ru') == 'утро'
    assert fix('xакер', 'ru') == 'хакер'


def test_uppercase_preserved():
    assert fix('Cепаратистов', 'ru') == 'Сепаратистов'
    assert fix('Dиректива', 'ru') == 'Директива'


def test_pure_latin_untouched():
    assert fix('FBI', 'ru') == 'FBI'
    assert fix('NATO', 'ru') == 'NATO'
    assert fix('iPhone', 'ru') == 'iPhone'


def test_pure_cyrillic_untouched():
    assert fix('обычное русское слово', 'ru') == 'обычное русское слово'


def test_noop_non_cyrillic_targets():
    assert fix('dирективы', 'pt') == 'dирективы'
    assert fix('dирективы', 'tr') == 'dирективы'


def test_mixed_inside_sentence():
    assert fix('Он видел dирективы и FBI', 'ru') == 'Он видел директивы и FBI'


def test_mid_word_latin_untouched():
    # Only the FIRST letter is a candidate; «фотo» (Latin o mid-word) stays.
    assert fix('фотo', 'ru') == 'фотo'


def test_unmapped_latin_letter_untouched():
    # 's' has no unambiguous Cyrillic homoglyph in the map — keep as is.
    assert fix('sлово', 'ru') == 'sлово'


def test_optional_map_b_h_m():
    assert fix('bыло', 'ru') == 'было'
    assert fix('hапример', 'ru') == 'например'
    assert fix('mоре', 'ru') == 'море'


def test_idempotent():
    once = fix('dирективы и tехнологии', 'ru')
    assert fix(once, 'ru') == once


def test_empty_and_none_lang():
    assert fix('', 'ru') == ''
    assert fix('dирективы', '') == 'dирективы'
    assert fix('dирективы', None) == 'dирективы'


def test_other_cyrillic_langs():
    assert fix('dирективи', 'uk') == 'директиви'
    assert fix('gрад', 'bg') == 'град'
    assert fix('tачка', 'sr') == 'тачка'
