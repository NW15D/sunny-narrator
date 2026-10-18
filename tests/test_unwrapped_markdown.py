"""
Markdown without soft wraps (pandoc --wrap=none) and the JSON answers of the
stages.

A cloud run had words in two alphabets ("dверей", "tихие", "gромкий") only
right after a "\\n" escape: pandoc wrapped every paragraph at ~72 characters,
each wrap became "\\n" inside the JSON the stages exchange, and Qwen wrote the
next word's first letter in Latin ("nd", "nt", "ng" are tokens). Now a
paragraph is one line; one longer than a chunk is cut at sentence ends, and
the translated halves of a cut inside a paragraph are joined with a space.

A JSON answer that never closes (cut off without finish_reason='length')
passed its raw text - '{"translation": "' and literal \\n - to the next stage;
now it fails the stage, so the chunk is split as for any truncated answer.
"""
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import markdown_utils as mu
from src import utils

SENTENCE = 'He said «Go now.» Then she left the room, closing the door. '


def _no_text_lost(pieces, line):
    return re.sub(r'[\s>]|^\d+\.', '', ''.join(pieces)) == re.sub(r'[\s>]|^\d+\.', '', line)


def test_a_paragraph_longer_than_a_chunk_is_cut_at_sentence_ends():
    line = (SENTENCE * 60).strip() + ' 他走了。她来了。'
    pieces = mu._split_long_line(line, 500)
    assert len(pieces) > 1 and all(len(p) <= 500 for p in pieces)
    assert all(p.endswith(('.', '!', '?', '»', '。')) for p in pieces[:-1])
    assert re.sub(r'\s', '', ''.join(pieces)) == re.sub(r'\s', '', line), "no text is lost"
    assert '«Go now.»' in pieces[1], "a closing quote stays with its sentence"


@pytest.mark.parametrize("prefix, cont", [("> ", "> "), ("> > ", "> > "), ("- ", "  "), ("12. ", "    ")])
def test_the_pieces_of_a_quote_or_a_list_item_stay_in_it(prefix, cont):
    pieces = mu._split_long_line(prefix + (SENTENCE * 30).strip(), 600)
    assert pieces[0].startswith(prefix) and all(p.startswith(cont) for p in pieces[1:])


def test_a_short_line_is_left_alone():
    assert mu._split_long_line("Short.", 500) == ["Short."]


def test_chunks_of_an_unwrapped_book_keep_their_size():
    text = "# Chapter\n\n" + (SENTENCE * 200).strip() + "\n\nShort paragraph."
    chunks = mu.split_markdown_structured(text, 2000)
    assert max(len(c) for c in chunks) <= 2000
    assert re.sub(r'\s', '', ''.join(chunks)) == re.sub(r'\s', '', text)


def test_halves_cut_inside_a_paragraph_are_joined_with_a_space(monkeypatch):
    calls = []

    def execute(**kw):
        calls.append(kw['source_text'])
        if len(calls) == 1:
            raise utils.TruncatedResponseError("cut off")
        return SimpleNamespace(final_translation=f"[{kw['source_text'].strip()}]", synopsis='',
                               synopsis_candidates=[], total_tokens=0, final_result=None)

    monkeypatch.setattr(utils._pipeline, 'execute', execute)
    monkeypatch.setattr(utils, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    paragraph = "One sentence here. " * 10 + "Last one."
    result, _ = utils.translate_chunk("english", "russian", paragraph, "", {}, [], "Россия")
    assert "\n" not in result and "] [" in result, "one paragraph, not two"


def test_halves_cut_at_a_paragraph_break_stay_two_paragraphs():
    assert utils._join_text_halves("First paragraph.\n\n") is None
    join = utils._join_text_halves("One. Two. ")
    assert join("Раз. Два.\n", "  Три.") == "Раз. Два. Три."


def test_an_unclosed_json_answer_fails_the_stage():
    with pytest.raises(utils.TruncatedResponseError, match="improve"):
        utils.remove_tags_with_check('{"translation": "Он сказал,\\nчто затем он', "improve")
    with pytest.raises(utils.TruncatedResponseError):
        utils.remove_tags_with_check('```json\n{"fixes": [{"find": "a", "replace": "b"', "reflection")


def test_answers_that_are_not_broken_json_pass():
    assert utils.remove_tags_with_check('{"translation": "Он ушёл.\\nКонец."}', "final") == "Он ушёл.\nКонец."
    assert utils.remove_tags_with_check("Простой текст {без json", "final") == "Простой текст {без json"
    assert utils.remove_tags_with_check("<ttext>Текст</ttext>", "final") == "Текст"


def test_the_regex_fallback_decodes_the_escapes():
    # an unescaped quote breaks json.loads; the newline must not stay "\n" letters
    assert utils.remove_tags('{"translation": "Он сказал "нет"\\nи ушёл"}') == 'Он сказал "нет"\nи ушёл'
