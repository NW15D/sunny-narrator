"""FB2 auto-repair must fix structure in place and never lose book text."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.fb2_handler as fb2
import src.fb2_repair as fb2_repair
import src.xmlcheck as xc
from src.fb2_repair import repair_fb2, repair_if_needed
from src.fb2_structure import visible_text

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
TAIL = '<p>Tail of part one after its sections (odd but seen in the wild).</p>'


def _valid_book():
    body, header, footer = fb2.parse_xml(RICH)
    body = body.replace(TAIL, '').replace('9lonely', 'lonely')
    return f"{header}<body>{body}</body>\n{footer}"


def _squash(s):
    return re.sub(r'\s+', '', s)


def test_fixture_book_is_schema_valid():
    assert xc.validate_fb2(_valid_book()) == []


def test_lost_closers_are_repaired_in_place_not_dumped_at_the_end():
    book = _valid_book()
    # lose one </p> and the </section> of chapter one (a nested section)
    broken = book.replace('H<sub>2</sub>O and x<sup>2</sup>.</p>', 'H<sub>2</sub>O and x<sup>2</sup>.', 1)
    start = broken.index('<section id="c1">')
    end = broken.index('</section>', start)
    broken = broken[:end] + broken[end + len('</section>'):]
    assert xc.validate_fb2(broken)

    repaired, repairs = repair_fb2(broken)

    assert _squash(repaired) == _squash(book)
    assert xc.validate_fb2(repaired) == []
    assert not re.search(r'(</section>\s*){3,}</body>', repaired)


def test_no_text_is_dropped_when_tags_are_broken():
    broken = ('<FictionBook><description/><body><section><p>keep <b>bold</p>'
              '<p>second & third</section></body></FictionBook>')
    repaired, _ = repair_fb2(broken)
    assert visible_text(repaired) == visible_text(broken)


def test_repair_is_rejected_if_it_would_change_the_text(monkeypatch):
    book = '<FictionBook xmlns="x"><body><section><p>abc</p></section></body></FictionBook>'
    monkeypatch.setattr(fb2_repair, 'repair_fragment', lambda *a, **k: '')
    repaired, repairs = repair_fb2(book)
    assert repaired == book
    assert repairs and 'rejected' in repairs[0].lower()


def test_junk_after_root_bom_and_missing_root_close():
    book = _valid_book()
    repaired, repairs = repair_fb2('﻿' + book + '\ntrailing junk')
    assert repaired.startswith('<?xml') and repaired.rstrip().endswith('</FictionBook>')
    assert 'junk' not in repaired
    assert xc.validate_fb2(repaired) == []

    truncated, _ = repair_fb2(book.rstrip()[:-len('</FictionBook>')])
    assert truncated.rstrip().endswith('</FictionBook>')


def test_repair_if_needed_leaves_valid_books_untouched_and_never_makes_things_worse():
    book = _valid_book()
    same, notes = repair_if_needed(book)
    assert same is book and notes == []

    broken = book.replace('<p>Direct text only.</p>', '<p>Direct text only.', 1)
    fixed, notes = repair_if_needed(broken)
    assert len(xc.validate_fb2(fixed)) < len(xc.validate_fb2(broken))
    assert any('Validation errors' in n for n in notes)


def test_lossy_helpers_are_gone():
    assert not hasattr(fb2_repair, '_fix_unclosed_tags')
    assert not hasattr(fb2_repair, '_balance_section_tags')


def test_write_to_file_honours_the_repair_flag(tmp_path):
    import app
    broken = _valid_book().replace('<p>Direct text only.</p>', '<p>Direct text only.', 1)
    plain, repaired = tmp_path / 'plain.fb2', tmp_path / 'fixed.fb2'
    app.write_to_file(broken, str(plain), auto_repair_fb2=False)
    app.write_to_file(broken, str(repaired), auto_repair_fb2=True)
    assert plain.read_text(encoding='utf-8') == broken
    assert len(xc.validate_fb2(repaired.read_text(encoding='utf-8'))) < len(xc.validate_fb2(broken))
