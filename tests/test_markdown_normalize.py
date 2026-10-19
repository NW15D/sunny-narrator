"""Tests for F2: idempotent markdown heading normalization (pandoc TOC fix).

LLM output sometimes contains '#Head' (no space after the hashes) or a
heading glued to the previous paragraph. Pandoc then leaves '#' as
visible text and toc.ncx ends up empty. normalize_markdown_headings()
must fix both, leave non-heading '#' alone, and be idempotent.

The fix is purely structural and must NOT be tied to a language pair:
no 'Глава'/'Chapter' hardcoding anywhere, tested across Cyrillic, Latin,
CJK, Arabic, Greek and Hebrew scripts (see TestAlphabetAgnostic).
"""
import pytest

from src.markdown_utils import normalize_markdown_headings


class TestMissingSpaceAfterHashes:
    def test_h1_no_space(self):
        assert normalize_markdown_headings('#Head') == '# Head'

    def test_h2_no_space(self):
        assert normalize_markdown_headings('##Глава') == '## Глава'

    def test_deep_level_no_space(self):
        assert normalize_markdown_headings('#####Part') == '##### Part'

    def test_already_spaced_unchanged(self):
        assert normalize_markdown_headings('# Head') == '# Head'


class TestBlankLineBeforeHeading:
    def test_heading_glued_to_paragraph(self):
        out = normalize_markdown_headings('Текст абзаца\n# Глава 2\nДальше.')
        assert out == 'Текст абзаца\n\n# Глава 2\nДальше.'

    def test_glued_and_squashed_combined(self):
        out = normalize_markdown_headings('строка\n##Глава')
        assert out == 'строка\n\n## Глава'

    def test_existing_blank_line_not_doubled(self):
        text = 'Параграф\n\n# Глава\n\nТекст'
        assert normalize_markdown_headings(text) == text


class TestNonHeadingHashesUntouched:
    def test_hash_inside_text(self):
        text = 'обычный текст # не заголовок'
        assert normalize_markdown_headings(text) == text

    def test_hashes_mid_line(self):
        text = 'текст ### внутри строки и #### ещё'
        assert normalize_markdown_headings(text) == text


class TestIdempotence:
    def test_double_application_stable(self):
        messy = 'Вступление\n#Глава 1\n## Часть\nтекст\n####Подчасть'
        once = normalize_markdown_headings(messy)
        assert normalize_markdown_headings(once) == once

    def test_double_application_on_clean_text(self):
        clean = '# H1\n\nПараграф\n\n## H2\n\nЕщё'
        assert normalize_markdown_headings(normalize_markdown_headings(clean)) == clean


class TestAlphabetAgnostic:
    """Requirement (Nick): the fix must work for ANY alphabet, not just
    Cyrillic ru->en history; no language-specific patterns allowed."""

    @pytest.mark.parametrize('raw,expected', [
        ('#Глава вторая', '# Глава вторая'),   # Cyrillic
        ('#Chapter two', '# Chapter two'),      # Latin
        ('#第二章节', '# 第二章节'),                # CJK
        ('#الفصل الثاني', '# الفصل الثاني'),      # Arabic
        ('#Κεφάλαιο', '# Κεφάλαιο'),            # Greek
        ('#פרק', '# פרק'),                       # Hebrew
        ('##ララ章', '## ララ章'),                 # Japanese kana/kanji
    ])
    def test_space_inserted_for_any_alphabet(self, raw, expected):
        assert normalize_markdown_headings(raw) == expected

    @pytest.mark.parametrize('text', [
        'Some paragraph.\n#Chapter two\nMore text.',
        'Текст абзаца.\n#Глава вторая\nДальше.',
        '段落。\n#第二章\n后续。',
        'نص.\n#الفصل\nبقية.',
    ])
    def test_blank_line_inserted_for_any_alphabet(self, text):
        out = normalize_markdown_headings(text)
        assert '\n\n#' in out
        assert normalize_markdown_headings(out) == out


def test_hashes_before_a_digit_or_a_sign_are_not_headings():
    from src.markdown_utils import normalize_markdown_headings
    text = "text\n#1 bestseller\n#!/bin/sh"
    assert normalize_markdown_headings(text) == text


def test_fenced_code_is_left_alone():
    from src.markdown_utils import normalize_markdown_headings
    text = "text\n\n```\n#Comment\n# another\n```\n\n#Real"
    assert normalize_markdown_headings(text) == "text\n\n```\n#Comment\n# another\n```\n\n# Real"


def test_a_lone_hash_line_is_not_counted_as_a_heading():
    from src.calibre_pipeline import count_markdown_headings
    assert count_markdown_headings("#\nsome text\n# A\n```\n# code\n```") == ["# A"]
