"""Rechunking split for the Calibre (Markdown) pipeline: never mid-word."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils import split_text_smartly


def _check(text):
    a, b = split_text_smartly(text)
    assert a + b == text
    assert a.strip() and b.strip()
    return a, b


def test_paragraph_break_is_preferred():
    paras = [f'Paragraph {i}. ' + 'Some words here. ' * 8 for i in range(6)]
    a, b = _check('\n\n'.join(paras))
    assert a.endswith('\n\n') and b.startswith('Paragraph 3.')


def test_sentence_end_without_paragraph_breaks():
    text = ' '.join(f'Sentence number {i} is here.' for i in range(40))
    a, b = _check(text)
    assert a.endswith('here. ') and b.startswith('Sentence number')


@pytest.mark.parametrize('end', ['?', '!', '…', '.»', '."', '.)'])
def test_other_sentence_ends(end):
    text = ' '.join(f'Line {i} ends{end}' for i in range(40))
    a, _ = _check(text)
    assert a.rstrip().endswith(end)


def test_cjk_sentence_end():
    text = ''.join(f'这是第{i}个句子。' for i in range(40))
    a, b = _check(text)
    assert a.endswith('。') and b.startswith('这是第')


def test_after_a_closing_tag():
    text = ''.join(f'<p>text {i} with no sentence punctuation</p>' for i in range(20))
    a, b = _check(text)
    assert a.endswith('</p>') and b.startswith('<p>')


def test_never_inside_a_tag():
    text = 'word ' * 50 + '<span class="a b c d e f g h i j k l m n o p q r s t">' + ' word' * 50
    a, b = _check(text)
    assert a.count('<') == a.count('>')


def test_never_inside_a_code_fence():
    prose = ' '.join(f'Sentence {i} is here.' for i in range(12))
    code = '```\n' + '\n\n'.join(f'x = {i}' for i in range(12)) + '\n```'
    text = prose + '\n\n' + code + '\n\n' + prose
    a, b = _check(text)
    assert a.count('```') % 2 == 0 and b.count('```') % 2 == 0


def test_between_words_when_nothing_better_exists():
    text = ' '.join(['word'] * 200)
    a, b = _check(text)
    assert a.endswith(' ') and not b.startswith(' ') and b.startswith('word')


def test_placeholders_are_never_cut():
    text = ' '.join(f'![](sn-imgref-{i}) caption {i}' for i in range(60))
    a, b = _check(text)
    assert not a.endswith('![](') and b.split()[0].startswith(('![](sn-imgref-', 'caption'))


def test_fallback_to_the_middle_for_unbreakable_text():
    text = '这' * 3000
    a, b = split_text_smartly(text)
    assert a + b == text and len(a) == 1500


def test_cut_stays_in_the_central_half():
    text = 'Short. ' + 'x' * 1000 + ' tail.'
    a, _ = _check(text)
    assert 0.25 * len(text) <= len(a) <= 0.75 * len(text)


def test_empty():
    assert split_text_smartly('') == ('', '')
