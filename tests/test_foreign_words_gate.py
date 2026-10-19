"""
Gate for transliterations and foreign words.

The improve stage may leave whole words of the other alphabet in the
translation ("dazhe", "desyatki", "tela", "telo-nositely" in a Russian
one; Cyrillic words in a Latin target). Which alphabet is "the other"
comes from target_lang (ru -> Cyrillic, en -> Latin; variants like
'pt-BR' or 'sr-Latn' included), never from a fixed pair.
find_unexpected_foreign_words finds them while the words a translation
keeps on purpose stay: the run's vocabulary, the basic list ("magnum
opus") and all-caps abbreviations of up to MAX_ABBREV_LEN
letters ("NASA"). Mixed-alphabet
words ("d\u043e\u043c\u0438\u043d\u0438\u043e\u043d\u043e\u0432") are the subject of
find_mixed_words. v1 warns and counts; it never blocks or retries a
translation.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import script_guard as sg


class _Ctx:
    """The TranslationContext fields the foreign-words note reads."""

    def __init__(self, target_lang='ru', vocab_entries=(), vocab_dict=None):
        self.target_lang = target_lang
        self.vocab_entries = list(vocab_entries)
        self.vocab_dict = dict(vocab_dict or {})


def test_transliterations_from_the_improve_stage_are_found():
    text = "\u041e\u043d \u043f\u0440\u043e\u0435\u0445\u0430\u043b dazhe \u043d\u0430 desyatki \u043a\u0438\u043b\u043e\u043c\u0435\u0442\u0440\u043e\u0432: tela \u0438 telo-nositely \u043f\u0435\u0440\u0435\u0432\u043e\u0437\u0438\u043b\u0438 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e."
    found = sg.find_unexpected_foreign_words(text, 'ru')
    assert {w.lower() for w in found} == {'dazhe', 'desyatki', 'tela', 'telo', 'nositely'}


def test_vocabulary_words_are_not_flagged():
    text = "\u0420\u0430\u043a\u0435\u0442\u0430 SpaceX \u043b\u0435\u0442\u0438\u0442 \u043a \u041c\u0430\u0440\u0441\u0443."
    assert sg.find_unexpected_foreign_words(text, 'ru', ['SpaceX']) == []
    # without the vocabulary the same word is a slip
    assert sg.find_unexpected_foreign_words(text, 'ru') == ['SpaceX']


def test_the_basic_latin_list_is_not_flagged():
    text = "Это его magnum opus."
    assert sg.find_unexpected_foreign_words(text, 'ru') == []


def test_a_lone_latin_letter_is_a_slip_not_a_foreign_word():
    # "a" for the Russian conjunction "а", "A" for "А"
    assert sg.find_unexpected_foreign_words("Он ушёл, a она осталась. A потом", 'ru') == ['a', 'A']


def test_all_caps_abbreviations_up_to_five_letters_are_not_flagged():
    text = "NASA \u0438 GRU \u0437\u0430\u044f\u0432\u0438\u043b\u0438, \u0430 BRUSSELS \u043c\u043e\u043b\u0447\u0430\u043b."
    assert sg.find_unexpected_foreign_words(text, 'ru') == ['BRUSSELS']


def test_mixed_alphabet_words_are_not_whole_foreign_words():
    text = "\u041d\u0430\u0441\u0435\u043b\u0435\u043d\u0438\u0435 d\u043e\u043c\u0438\u043d\u0438\u043e\u043d\u043e\u0432 \u0438 t\u0443\u043d\u0438\u043a\u0438 \u0440\u043e\u0441\u043b\u043e."
    assert sg.find_mixed_words(text, 'ru') == ['d\u043e\u043c\u0438\u043d\u0438\u043e\u043d\u043e\u0432', 't\u0443\u043d\u0438\u043a\u0438']
    assert sg.find_unexpected_foreign_words(text, 'ru') == []


@pytest.mark.parametrize("target,text,expected", [
    # a Cyrillic target: whole words of the Latin alphabet are the slip
    ('ru', "\u041e\u043d \u043f\u0440\u043e\u0435\u0445\u0430\u043b dazhe \u043d\u0430 desyatki \u043a\u0438\u043b\u043e\u043c\u0435\u0442\u0440\u043e\u0432.", {'dazhe', 'desyatki'}),
    ('russian', "\u041e\u043d \u0443\u0435\u0445\u0430\u043b vchera.", {'vchera'}),
    # a Latin target (variants included): the Cyrillic words are the slip
    ('en', "He said \u043f\u0440\u0438\u0432\u0435\u0442 and \u041f\u043e\u043a\u0430 to everyone.", {'\u043f\u0440\u0438\u0432\u0435\u0442', '\u043f\u043e\u043a\u0430'}),
    ('french', "Il a dit \u043f\u0440\u0438\u0432\u0435\u0442.", {'\u043f\u0440\u0438\u0432\u0435\u0442'}),
    ('pt-BR', "Ele disse \u043f\u0440\u0438\u0432\u0435\u0442.", {'\u043f\u0440\u0438\u0432\u0435\u0442'}),
])
def test_the_slip_alphabet_comes_from_the_target(target, text, expected):
    found = sg.find_unexpected_foreign_words(text, target)
    assert {w.lower() for w in found} == expected


def test_a_latin_target_keeps_abbreviations_and_skips_the_vocabulary():
    assert sg.find_unexpected_foreign_words("Yuri \u0413\u0430\u0433\u0430\u0440\u0438\u043d and the UN flew.", 'en', ['\u0413\u0430\u0433\u0430\u0440\u0438\u043d']) == []
    assert sg.find_unexpected_foreign_words("Yuri \u0413\u0430\u0433\u0430\u0440\u0438\u043d flew.", 'en') == ['\u0413\u0430\u0433\u0430\u0440\u0438\u043d']
    # all-caps abbreviations stay in either direction
    assert sg.find_unexpected_foreign_words("The UN and \u041d\u0410\u0422\u041e met.", 'en') == []


@pytest.mark.parametrize("target,text,expected", [
    ('ru', "\u041d\u0430\u0441\u0435\u043b\u0435\u043d\u0438\u0435 d\u043e\u043c\u0438\u043d\u0438\u043e\u043d\u043e\u0432 \u0438 t\u0443\u043d\u0438\u043a\u0438 \u0440\u043e\u0441\u043b\u043e.", ['d\u043e\u043c\u0438\u043d\u0438\u043e\u043d\u043e\u0432', 't\u0443\u043d\u0438\u043a\u0438']),
    ('fr', "Il \u00e9tait tr\u00e8\u0455 fatigu\u00e9.", ['tr\u00e8\u0455']),
])
def test_mixed_words_for_a_cyrillic_and_a_latin_target(target, text, expected):
    assert sg.find_mixed_words(text, target) == expected


@pytest.mark.parametrize("lang,expected", [
    ('ru', 'CYRILLIC'), ('russian', 'CYRILLIC'), ('uk', 'CYRILLIC'), ('kk-KZ', 'CYRILLIC'),
    ('en', 'LATIN'), ('en-GB', 'LATIN'), ('french', 'LATIN'), ('pt-BR', 'LATIN'),
    ('sr', 'CYRILLIC'), ('sr-Latn', 'LATIN'), ('sr-Cyrl', 'CYRILLIC'),
    ('el', 'GREEK'),
    ('zh-CN', None), ('japanese', None), ('chinese', None),
])
def test_the_script_comes_from_the_language_and_its_variant(lang, expected):
    assert sg.target_script(lang) == expected


def test_note_foreign_words_reports_to_the_metrics(monkeypatch):
    from src import utils

    class _FakeMetrics:
        def __init__(self):
            self.calls = []

        def log_foreign_words(self, words, stage=""):
            self.calls.append((stage, list(words)))

    fake = _FakeMetrics()
    monkeypatch.setattr(utils, 'metrics', fake)
    utils._note_foreign_words("\u041e\u043d \u043f\u043e\u0435\u0445\u0430\u043b dazhe \u0434\u043e\u043c\u043e\u0439", _Ctx(), "improve_translation")
    assert fake.calls == [("improve_translation", ["dazhe"])]
    utils._note_foreign_words("\u041e\u043d \u043f\u043e\u0435\u0445\u0430\u043b \u0434\u043e\u043c\u043e\u0439", _Ctx(), "final_edit")
    assert fake.calls == [("improve_translation", ["dazhe"])]


@pytest.mark.parametrize("lang", ["zh-CA", "zh-ID", "ar-FR", "ko-DE"])
def test_a_region_that_is_a_latin_language_code_does_not_make_the_target_latin(lang):
    assert sg.target_script(lang) is None
