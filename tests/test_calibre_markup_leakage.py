"""Markup from the source EPUB must not reach the reader as text.

Every string in this file is taken from a real translated EPUB, where these
constructs appeared as visible lines of the book:

    ::: {link="blue" vlink="purple"} 1 =
    <span id="freeText8134770031895557530" style="">
    <a class="actionLinkLite" href="http://www.goodreads.com/book/show/...#"></a>

They start as ordinary markup in a scraped source EPUB, survive pandoc's
HTML->Markdown pass as raw HTML or as a fenced div, reach the translation LLM
looking like prose, and come back with the straight quotes rewritten as
typographic ones — at which point they no longer parse as markup and get
rendered literally. See _sanitize_source_html for the full chain.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402

from src.calibre_pipeline import (  # noqa: E402
    _init_logger,
    _PANDOC_MD_FORMAT,
    _clean_calibre_markers,
    _protect_markdown_html,
    _restore_markdown_html,
    _sanitize_source_html,
)



@pytest.fixture(autouse=True)
def _logger():
    """calibre_pipeline's module logger is created lazily by the pipeline
    entry points, so anything calling a helper directly must set it up first
    (same pattern as test_calibre_image_protection)."""
    _init_logger()


# --- A1: sanitizing the source HTML ----------------------------------------

def test_sanitize_drops_empty_tracking_anchor():
    html = ('<p>Text<a class="actionLinkLite" '
            'href="http://www.goodreads.com/book/show/10648878#"></a></p>')
    out = _sanitize_source_html(html)
    assert 'goodreads' not in out
    assert 'Text' in out


def test_sanitize_keeps_anchors_that_carry_text():
    html = '<p><a href="http://example.com">real link</a></p>'
    out = _sanitize_source_html(html)
    assert 'real link' in out
    assert 'href="http://example.com"' in out


def test_sanitize_keeps_anchors_wrapping_an_image():
    html = '<p><a href="x.html"><img src="pic.jpg" alt="cover"/></a></p>'
    out = _sanitize_source_html(html)
    assert 'pic.jpg' in out


def test_sanitize_unwraps_id_only_span_but_keeps_its_text():
    html = ('<p><span id="freeText8134770031895557530" style="">'
            'chapter text</span></p>')
    out = _sanitize_source_html(html)
    assert 'freeText8134770031895557530' not in out
    assert '<span' not in out
    assert 'chapter text' in out


def test_sanitize_strips_legacy_body_attributes_that_become_fenced_divs():
    """`<div link=... vlink=...>` is what pandoc turns into `::: {link=...}`."""
    html = '<div link="blue" vlink="purple"><p>Body</p></div>'
    out = _sanitize_source_html(html)
    assert 'vlink' not in out
    assert '<div' not in out
    assert 'Body' in out


def test_sanitize_preserves_headings_needed_for_the_toc():
    html = '<div class="x"><h1 id="c1">Chapter One</h1><h2>Part</h2></div>'
    out = _sanitize_source_html(html)
    assert '<h1' in out and 'Chapter One' in out
    assert '<h2>Part</h2>' in out
    assert 'class="x"' not in out


def test_sanitize_removes_script_and_style():
    html = '<p>a</p><script>evil()</script><style>p{color:red}</style>'
    out = _sanitize_source_html(html)
    assert 'evil()' not in out and 'color:red' not in out


def test_sanitize_never_raises_on_garbage():
    for bad in ('', '   ', '<p>unclosed', '<<<>>>'):
        assert isinstance(_sanitize_source_html(bad), str)


# --- A2: pandoc writer must not re-encode markup ---------------------------

def test_pandoc_markdown_writer_disables_markup_passthrough():
    for ext in ('raw_html', 'native_divs', 'native_spans', 'fenced_divs'):
        assert f'-{ext}' in _PANDOC_MD_FORMAT, (
            f"pandoc would re-encode markup via '{ext}'; that is what puts "
            f"'::: {{...}}' and raw <span> into the translated text"
        )


# --- A3: post-hoc cleanup ---------------------------------------------------

def test_clean_removes_fenced_div_with_straight_quotes():
    assert '::: ' not in _clean_calibre_markers('::: {link="blue" vlink="purple"}\n\nText')


def test_clean_removes_fenced_div_with_typographic_quotes():
    """The exact form seen in the shipped book: the LLM rewrote the quotes."""
    text = '::: {link=“blue” vlink=“purple”} 1 =\n\nText'
    out = _clean_calibre_markers(text)
    assert ':::' not in out
    assert 'vlink' not in out
    assert 'Text' in out


def test_clean_keeps_line_content_after_the_fence_marker():
    out = _clean_calibre_markers('::: {.foo} surviving words\n\nmore')
    assert 'surviving words' in out


def test_clean_removes_empty_inline_wrappers():
    text = '<span id="freeText1"></span>Body<a class="actionLinkLite" href="#"></a>'
    out = _clean_calibre_markers(text)
    assert '<span' not in out and '<a ' not in out
    assert 'Body' in out


def test_clean_removes_nested_empty_wrappers():
    out = _clean_calibre_markers('<span id="x"><a href="#"></a></span>Body')
    assert '<span' not in out and '<a ' not in out
    assert 'Body' in out


def test_clean_leaves_real_markdown_alone():
    md = '# Chapter\n\nSome *text* with [a link](http://x) and a colon: here.\n'
    assert 'Chapter' in _clean_calibre_markers(md)
    assert '[a link](http://x)' in _clean_calibre_markers(md)


# --- A4: protecting what is left through the LLM ---------------------------

def test_protect_and_restore_raw_html_roundtrip():
    md = 'Before <span id="freeText8134770031895557530"> after </span> end.'
    protected, bits = _protect_markdown_html(md)
    assert '<span' not in protected
    assert len(bits) == 2
    assert _restore_markdown_html(protected, bits) == md


def test_protected_html_placeholder_is_not_prose():
    md = 'Text <br/> more'
    protected, _ = _protect_markdown_html(md)
    assert 'sn-htmlref-0' in protected


def test_protect_preserves_order_of_multiple_tags():
    md = '<p>one</p><div>two</div><p>three</p>'
    protected, bits = _protect_markdown_html(md)
    assert _restore_markdown_html(protected, bits) == md


def test_protect_leaves_img_tags_to_the_image_protector():
    md = 'x <img src="pic.jpg"> y'
    protected, bits = _protect_markdown_html(md)
    assert bits == []
    assert protected == md


def test_protect_ignores_prose_that_merely_contains_angle_brackets():
    md = 'The value a < b and the address <nobody@example.com> stay put.'
    protected, bits = _protect_markdown_html(md)
    assert bits == []
    assert protected == md


def test_restore_warns_when_the_llm_lost_a_placeholder(caplog):
    import logging
    protected, bits = _protect_markdown_html('a <b> c')
    mangled = protected.replace('[](sn-htmlref-0)', '')
    with caplog.at_level(logging.WARNING):
        _restore_markdown_html(mangled, bits)
    assert any('Raw HTML restoration mismatch' in r.message for r in caplog.records)


def test_restore_tolerates_out_of_range_placeholder():
    out = _restore_markdown_html('text [](sn-htmlref-9) text', ['<b>'])
    assert 'sn-htmlref-9' in out


def test_html_and_image_placeholders_do_not_collide():
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = 'See ![cover](images/pic.jpg) and <span id="x">note</span>.'
    step1, images = _protect_markdown_images(md)
    step2, html_bits = _protect_markdown_html(step1)
    assert html_bits, "the span must still be protected after image protection"
    restored = _restore_markdown_images(_restore_markdown_html(step2, html_bits), images)
    assert restored == md
