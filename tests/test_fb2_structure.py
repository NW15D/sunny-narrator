"""Structure-aware FB2 chunking and local tag repair (src/fb2_structure.py)."""
import os
import random
import sys

import pytest
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.fb2_handler as fb2
from src.fb2_structure import (
    chunk_unit_content,
    close_dangling_sections,
    prepare_body_structure,
    repair_fragment,
    sanitize_translated_chunk,
    section_transition,
    split_blocks,
    split_body_units,
    visible_text,
)

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
TAIL = '<p>Tail of part one after its sections (odd but seen in the wild).</p>'


def _rich_body(valid=False):
    body, _header, _footer = fb2.parse_xml(RICH)
    # the fixture deliberately carries a tail paragraph after sub-sections and a
    # digit-leading id (both invalid FB2, both seen in the wild)
    return body.replace(TAIL, '').replace('9lonely', 'lonely') if valid else body


def _rebuild(sections, meta):
    cur, out = 0, []
    for chunks, m in zip(sections, meta):
        text, cur = section_transition(m, cur)
        out.append(text)
        out.extend(c + '\n' for c in chunks)
    out.append('</section>\n' * cur)
    return ''.join(out)


def _squash(xml):
    import re
    return re.sub(r'\s+', '', xml)


def _well_formed(fragment):
    etree.fromstring(f'<r xmlns:l="http://www.w3.org/1999/xlink">{fragment}</r>')


# --------------------------------------------------------------------------
# Splitting the source
# --------------------------------------------------------------------------

def test_units_keep_preamble_nested_sections_and_tail():
    units = split_body_units(_rich_body())
    shape = [(u.open_tag, u.depth) for u in units]
    assert shape[0] == (None, 0)                     # body-level title + epigraph
    assert ('<section id="part1">', 1) in shape
    assert ('<section id="c1">', 2) in shape
    assert ('<section id="c2">', 2) in shape
    assert (None, 1) in shape                        # tail of part1 after its children
    assert shape[-1] == ('<section id="9lonely">', 1)
    assert 'The Rich Book' in units[0].content and 'Tail of part one' in ''.join(
        u.content for u in units if u.open_tag is None and u.depth == 1)


def test_body_without_sections_becomes_one_section():
    units = split_body_units('<p>a</p><p>b</p>')
    assert [(u.open_tag, u.depth) for u in units] == [('<section>', 1)]
    assert split_body_units('  \n') == []


def test_stray_closer_dropped_and_self_closing_section_kept():
    units = split_body_units('<section><p>a</p></section></section><section id="e"/><section><p>b</p></section>')
    assert [(u.open_tag, u.depth) for u in units] == [
        ('<section>', 1), ('<section id="e">', 1), ('<section>', 1)]
    assert 'a' in units[0].content and 'b' in units[2].content


def test_body_wrapper_tags_are_ignored():
    sections, meta = prepare_body_structure('<body><section id="x"><p>t</p></section></body>', 1000)
    assert meta == [{'open_tag': '<section id="x">', 'depth': 1, 'chunks': 1}]
    assert '<body' not in ''.join(''.join(s) for s in sections)


@pytest.mark.parametrize('max_len', [40, 90, 250, 8192])
def test_rebuild_is_lossless_and_keeps_the_tree(max_len):
    body = _rich_body()
    sections, meta = prepare_body_structure(body, max_len)
    rebuilt = _rebuild(sections, meta)
    assert visible_text(rebuilt) == visible_text(body)
    assert close_dangling_sections(rebuilt) == rebuilt
    assert rebuilt.count('<section') == rebuilt.count('</section>') == body.count('<section')
    assert '<section id="c1">' in rebuilt and '<section id="9lonely">' in rebuilt
    _well_formed(rebuilt)


@pytest.mark.parametrize('max_len', [40, 90, 250, 8192])
def test_every_chunk_is_balanced_on_its_own(max_len):
    sections, _meta = prepare_body_structure(_rich_body(), max_len)
    chunks = [c for s in sections for c in s]
    assert chunks
    for chunk in chunks:
        assert '<section' not in chunk
        assert repair_fragment(chunk) == chunk, chunk
        _well_formed(chunk)


def test_rebuilt_book_validates_against_the_fb2_schema():
    import src.xmlcheck as xc
    body = _rich_body(valid=True)
    _b, header, footer = fb2.parse_xml(RICH)
    sections, meta = prepare_body_structure(body, 90)
    xml = f"{header}<body>\n{_rebuild(sections, meta)}</body>\n{footer}"
    assert xc.validate_fb2(xml) == []


def test_poem_is_split_between_stanzas_never_inside_one():
    poem = ('<poem><title><p>T</p></title>'
            + ''.join(f'<stanza><v>line {i}a</v><v>line {i}b</v></stanza>' for i in range(6))
            + '<text-author>A</text-author></poem>')
    chunks = chunk_unit_content(poem, 120)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.startswith('<poem>') and chunk.endswith('</poem>')
        assert '<stanza>' in chunk                   # never a poem without stanzas
        assert repair_fragment(chunk) == chunk
    assert visible_text(''.join(chunks)) == visible_text(poem)
    assert chunks[0].startswith('<poem><title>')     # title stays with the first stanza
    assert chunks[-1].endswith('<text-author>A</text-author></poem>')


def test_oversized_paragraph_is_kept_whole():
    big = '<p>' + 'word ' * 500 + '</p>'
    assert chunk_unit_content('<p>a</p>' + big + '<p>b</p>', 100) == ['<p>a</p>', big, '<p>b</p>']


def test_split_blocks_top_level_only():
    text = '<title><p>t</p></title>\n<p>a <em>b</em></p><empty-line/><poem><stanza><v>x</v></stanza></poem>'
    assert [b.strip() for b in split_blocks(text)] == [
        '<title><p>t</p></title>', '<p>a <em>b</em></p>', '<empty-line/>',
        '<poem><stanza><v>x</v></stanza></poem>']


def test_close_dangling_sections_only_touches_the_tail():
    assert close_dangling_sections('<section>\n<p>a</p>\n') == '<section>\n<p>a</p>\n</section>\n'
    assert close_dangling_sections('<section><section><p>a</p>') == '<section><section><p>a</p>\n</section>\n</section>\n'
    assert close_dangling_sections('<p>x</p></section><section><p>y</p></section>') == '<p>x</p><section><p>y</p></section>'
    balanced = '<section><p>a</p></section>\n'
    assert close_dangling_sections(balanced) == balanced


# --------------------------------------------------------------------------
# Repairing translated chunks
# --------------------------------------------------------------------------

@pytest.mark.parametrize('broken, fixed', [
    ('<p>ok</p>\n<p>fine <strong>x</strong></p>', '<p>ok</p>\n<p>fine <strong>x</strong></p>'),
    ('<p>a<p>b<p>c</p>', '<p>a</p><p>b</p><p>c</p>'),
    ('<p>a</p></p><p>b</p>', '<p>a</p><p>b</p>'),
    ('<poem><stanza><v>a</v><v>b</stanza></poem>', '<poem><stanza><v>a</v><v>b</v></stanza></poem>'),
    ('<p><strong>a<em>b</strong>c</em></p>', '<p><strong>a<emphasis>b</emphasis></strong>c</p>'),
    ('plain\n\nsecond', '<p>plain</p>\n<p>second</p>'),
    ('<p>x</p> stray <p>y</p>', '<p>x</p><p>stray</p><p>y</p>'),
    ('<b>bold</b> <i>it</i><br/>', '<p><strong>bold</strong> <emphasis>it</emphasis></p>'),
    ('<p>1 < 2 & 3 &nbsp;!</p>', '<p>1 &lt; 2 &amp; 3 \xa0!</p>'),
    ('<p>x</p><section><p>y</p></section>', '<p>x</p><p>y</p>'),
    ('<title>Chapter</title><p>t</p>', '<title><p>Chapter</p></title><p>t</p>'),
])
def test_repair_fragment_fixes_locally(broken, fixed):
    assert repair_fragment(broken) == fixed


def test_a_lost_closer_is_repaired_where_it_was_lost_not_at_the_end():
    broken = '<p>one</p><p>two<p>three</p><p>four</p>'
    fixed = repair_fragment(broken)
    assert fixed == '<p>one</p><p>two</p><p>three</p><p>four</p>'
    assert not fixed.endswith('</p></p>')


def test_lost_section_closer_is_found_via_the_content_model():
    broken = ('<section id="a"><title><p>A</p></title><p>text a</p>'
              '<section id="b"><title><p>B</p></title><p>text b</p></section>')
    fixed = repair_fragment(broken, keep_sections=True)
    assert fixed == ('<section id="a"><title><p>A</p></title><p>text a</p></section>'
                     '<section id="b"><title><p>B</p></title><p>text b</p></section>')


def test_section_with_only_a_title_may_still_hold_sections():
    ok = '<section><title><p>Part</p></title><section><p>x</p></section><section><p>y</p></section></section>'
    assert repair_fragment(ok, keep_sections=True) == ok


def test_sanitize_strips_code_fences_and_collapses_blank_lines():
    assert sanitize_translated_chunk('```xml\n<p>a</p>\n\n\n<p>b</p>\n```') == '<p>a</p>\n\n<p>b</p>'


_TOKENS = ['<p>', '</p>', '<v>', '</v>', '<poem>', '</poem>', '<stanza>', '</stanza>',
           '<strong>', '</strong>', '<emphasis>', '</emphasis>', '<empty-line/>', '<image l:href="#x"/>',
           '<title>', '</title>', '<cite>', '</cite>', '<b>', '<br>', '<table>', '<tr>', '<td>', '</td>',
           '</tr>', '</table>', '<section>', '</section>', ' word ', 'text', ' a & b ', ' x < y ',
           '&nbsp;', '&amp;', '\n\n', 'Привет']


@pytest.mark.parametrize('keep_sections', [False, True])
def test_repair_fragment_fuzz_never_loses_text_and_always_yields_xml(keep_sections):
    rng = random.Random(20240929)
    for _ in range(400):
        text = ''.join(rng.choice(_TOKENS) for _ in range(rng.randint(1, 25)))
        fixed = repair_fragment(text, keep_sections=keep_sections)
        assert visible_text(fixed) == visible_text(text), (text, fixed)
        _well_formed(fixed)
        assert repair_fragment(fixed, keep_sections=keep_sections) == fixed, (text, fixed)
        if not keep_sections:
            assert 'section' not in fixed


# --------------------------------------------------------------------------
# Regressions from code review
# --------------------------------------------------------------------------

@pytest.mark.parametrize('fragment', [
    '<table><tr><td>A</td><td/><td>C</td></tr></table>',
    '<p>a</p><p/><p>b</p>',
    '<p>x<strong/>y</p>',
])
def test_self_closed_elements_are_kept(fragment):
    assert repair_fragment(fragment) == fragment


def test_empty_anchor_section_is_kept_in_book_level_repair():
    body = '<section id="n4"><p>a</p></section><section id="n5"/><section id="n6"><p>b</p></section>'
    assert repair_fragment(body, keep_sections=True, strip_unknown=False) == body


def test_self_closed_block_still_closes_an_open_paragraph():
    assert repair_fragment('<p>a<p/>b</p>') == '<p>a</p><p/><p>b</p>'


def test_split_container_keeps_its_id_only_once():
    cite = '<cite id="c1">' + ''.join(f'<p>paragraph {i} ' + 'x' * 40 + '</p>' for i in range(6)) + '</cite>'
    chunks = chunk_unit_content(cite, 120)
    assert len(chunks) > 1
    assert ''.join(chunks).count('id="c1"') == 1
    assert chunks[0].startswith('<cite id="c1">')
    assert all(c.startswith('<cite>') for c in chunks[1:])


@pytest.mark.parametrize('broken, fixed', [
    ('Hello <emphasis>world</emphasis> again', '<p>Hello <emphasis>world</emphasis> again</p>'),
    ('one\n\n<emphasis>two</emphasis>', '<p>one</p>\n<p><emphasis>two</emphasis></p>'),
    ('<p>x</p> stray <p>y</p>', '<p>x</p><p>stray</p><p>y</p>'),
])
def test_wrapping_keeps_word_boundaries(broken, fixed):
    assert repair_fragment(broken) == fixed


@pytest.mark.parametrize('prose', [
    '<p>if a<b and c>d then</p>',
    '<p>x <i am not a tag> y</p>',
    '<p>arrow <= and <p but not a tag</p>',
])
def test_tag_like_prose_is_escaped_not_turned_into_markup(prose):
    fixed = sanitize_translated_chunk(prose)
    _well_formed(fixed)
    assert visible_text(fixed) == visible_text(prose)
    assert '<strong' not in fixed and '<emphasis' not in fixed


def test_split_in_two_cuts_between_blocks_and_stanzas():
    from src.fb2_structure import split_in_two
    paras = ''.join(f'<p>para {i} text text</p>' for i in range(10))
    head, tail = split_in_two(paras)
    assert head + tail == paras and head.endswith('</p>') and tail.startswith('<p>')
    assert abs(len(head) - len(tail)) < len('<p>para 0 text text</p>') * 2

    poem = '<poem>' + ''.join(f'<stanza><v>l{i}</v><v>m{i}</v></stanza>' for i in range(8)) + '</poem>'
    head, tail = split_in_two(poem)
    for part in (head, tail):
        assert part.startswith('<poem>') and part.endswith('</poem>')
        assert repair_fragment(part) == part
    assert visible_text(head + tail) == visible_text(poem)

    single = '<p>' + 'word ' * 600 + '</p>'
    assert split_in_two(single) == (single, '')


@pytest.mark.parametrize('broken, fixed', [
    ('<p>line one<br>line two</p>', '<p>line one</p>\n<p>line two</p>'),
    ('<v>строка<br/>вторая</v>', '<v>строка</v>\n<v>вторая</v>'),
    ('<p><emphasis>a<br/>b</emphasis> c</p>', '<p><emphasis>a</emphasis></p>\n<p><emphasis>b</emphasis> c</p>'),
    ('<p>trailing<br/></p><p>next</p>', '<p>trailing</p><p>next</p>'),
    ('word<br>word', '<p>word</p>\n<p>word</p>'),
    ('<poem><stanza><v>a<br>b</v></stanza></poem>', '<poem><stanza><v>a</v>\n<v>b</v></stanza></poem>'),
])
def test_br_breaks_the_paragraph_instead_of_gluing_words(broken, fixed):
    result = repair_fragment(broken)
    assert result == fixed
    assert repair_fragment(result) == result
    _well_formed(result)
