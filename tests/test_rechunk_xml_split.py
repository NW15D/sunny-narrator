"""Length-based rechunking of FB2 chunks must split between blocks."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as utils
from src.fb2_structure import repair_fragment


def _run(monkeypatch, source, style):
    seen = []

    def fake_execute(**kw):
        seen.append(kw['source_text'])
        text = kw['source_text']
        # first call: absurdly long translation to force a split; halves: identity
        out = text * 10 if len(seen) == 1 else text
        return SimpleNamespace(final_translation=out, synopsis='', synopsis_candidates=[], total_tokens=0)

    monkeypatch.setattr(utils._pipeline, 'execute', fake_execute)
    result, _ = utils.translate_chunk('en', 'ru', source, '', {}, style=style)
    return seen, result


def test_xml_chunk_is_split_into_well_formed_halves(monkeypatch):
    poem = '<poem>' + ''.join(f'<stanza><v>line {i} ' + 'x' * 120 + '</v></stanza>' for i in range(20)) + '</poem>'
    seen, result = _run(monkeypatch, poem, 'xml')
    assert len(seen) == 3
    for half in seen[1:]:
        assert half.startswith('<poem>') and half.endswith('</poem>')
        assert repair_fragment(half) == half


def test_single_block_xml_chunk_is_not_split(monkeypatch):
    para = '<p>' + 'word ' * 600 + '</p>'
    seen, result = _run(monkeypatch, para, 'xml')
    assert seen == [para]
    assert result == para * 10


def test_text_style_still_uses_the_old_splitter(monkeypatch):
    text = '\n\n'.join('Sentence number %d. ' % i * 10 for i in range(20))
    seen, _ = _run(monkeypatch, text, 'text')
    assert len(seen) == 3 and seen[1] + seen[2] == text


def test_huge_paragraph_is_split_at_a_sentence_and_joined_back(monkeypatch):
    sentences = [f'Sentence {i} has <emphasis>some words</emphasis> in it. ' for i in range(80)]
    para = '<p id="big">' + ''.join(sentences).strip() + '</p>'
    seen, result = _run(monkeypatch, para, 'xml')
    assert len(seen) == 3
    first, second = seen[1], seen[2]
    assert first.startswith('<p id="big">') and first.endswith('.</p>')
    assert second.startswith('<p>Sentence ') and second.endswith('</p>')
    for half in (first, second):
        assert repair_fragment(half) == half              # never cut inside <emphasis>
    assert result.count('<p') == 1 and result.count('</p>') == 1
    assert result.startswith('<p id="big">') and 'in it. Sentence' in result
    assert result.count('Sentence ') == 80


def test_paragraph_halves_that_came_back_as_several_blocks_are_kept_apart():
    from src.fb2_structure import join_paragraph_halves
    assert join_paragraph_halves('<p>A.</p>', '<p>B.</p><p>C.</p>') == '<p>A.</p>\n<p>B.</p><p>C.</p>'
    assert join_paragraph_halves('<p>A.</p>', '<p>B.</p>') == '<p>A. B.</p>'
