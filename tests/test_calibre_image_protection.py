"""Markdown image references must survive translation unchanged.

The translation LLM receives raw markdown chunks; asking it to translate a
chunk containing `![alt](images/foo.jpg)` risks the reference being dropped
or mangled, silently losing the image from the final EPUB. calibre_pipeline
swaps image markup for opaque placeholders before translation and restores
them afterwards - these tests cover that round trip.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_protect_and_restore_single_image():
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = "Some text.\n\n![Illustration](images/pic1.jpg)\n\nMore text."
    protected, images = _protect_markdown_images(md)

    assert "![Illustration](images/pic1.jpg)" not in protected
    assert images == ["![Illustration](images/pic1.jpg)"]

    restored = _restore_markdown_images(protected, images)
    assert restored == md


def test_protect_and_restore_multiple_images_preserves_order():
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = (
        "![First](images/a.png)\n\n"
        "Text between images.\n\n"
        "![Second](images/b.png \"title\")\n"
    )
    protected, images = _protect_markdown_images(md)
    assert len(images) == 2

    # Placeholders survive being embedded in "translated" surrounding text.
    translated_like = protected.replace("Text between images.", "Texte entre les images.")
    restored = _restore_markdown_images(translated_like, images)

    assert "![First](images/a.png)" in restored
    assert "![Second](images/b.png \"title\")" in restored
    assert restored.index("![First]") < restored.index("![Second]")


def test_protect_no_images_is_noop():
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = "Just plain text, no pictures here."
    protected, images = _protect_markdown_images(md)
    assert protected == md
    assert images == []
    assert _restore_markdown_images(protected, images) == md


def test_placeholder_is_valid_markdown_image_syntax():
    """The placeholder itself must be recognizable as a markdown image
    (![](...)), not an opaque token — this is what keeps
    markdown_utils.parse_structural_blocks() treating the line as a
    standalone image block during chunking instead of gluing it into a
    regular paragraph mid-sentence."""
    from src.calibre_pipeline import _protect_markdown_images, _RE_MD_IMAGE

    protected, images = _protect_markdown_images("![alt](images/pic.jpg)")
    assert len(images) == 1
    assert _RE_MD_IMAGE.match(protected), (
        f"placeholder {protected!r} is not itself valid markdown image syntax"
    )


def test_restore_accepts_legacy_invisible_separator_placeholder():
    """.translated.md dumps written before the placeholder format changed
    (from the opaque "⁣IMGREFn⁣" token to "![](sn-imgref-n)") must still
    restore correctly."""
    from src.calibre_pipeline import _restore_markdown_images

    legacy = "Text.\n\n⁣IMGREF0⁣\n\nMore text."
    restored = _restore_markdown_images(legacy, ["![alt](images/pic.jpg)"])
    assert restored == "Text.\n\n![alt](images/pic.jpg)\n\nMore text."


def test_restore_warns_on_mismatch(caplog):
    """If a placeholder is lost/mangled during translation (survives
    neither the current nor legacy form), _restore_markdown_images must not
    fail silently — the whole point of tracking this is so a lost image
    shows up in the server log instead of only being noticed by opening the
    finished book."""
    import logging
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images, _init_logger

    _init_logger()
    protected, images = _protect_markdown_images(
        "![A](images/a.jpg)\n\n![B](images/b.jpg)"
    )
    # Simulate the LLM mangling one placeholder beyond recognition.
    mangled = protected.replace("sn-imgref-1", "sn-img-ref-1 (garbled)")

    with caplog.at_level(logging.WARNING, logger="src.calibre_pipeline"):
        restored = _restore_markdown_images(mangled, images)

    assert "![A](images/a.jpg)" in restored
    assert "![B](images/b.jpg)" not in restored  # lost, as expected
    messages = [r.getMessage() for r in caplog.records if r.name == "src.calibre_pipeline"]
    assert any("mismatch" in m.lower() for m in messages)


def test_protect_raw_html_img_tag():
    """Pandoc occasionally emits a raw <img> tag instead of markdown image
    syntax; these must be protected too, not just "![...](...)" refs."""
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = 'Before.\n\n<img src="images/pic.jpg" alt="x"/>\n\nAfter.'
    protected, images = _protect_markdown_images(md)
    assert '<img src="images/pic.jpg" alt="x"/>' not in protected
    assert images == ['<img src="images/pic.jpg" alt="x"/>']
    assert _restore_markdown_images(protected, images) == md


def test_protect_alt_text_with_nested_brackets():
    """Alt text containing a bracketed footnote-style ref (e.g. "[1]") must
    not truncate the match at the inner "]"."""
    from src.calibre_pipeline import _protect_markdown_images, _restore_markdown_images

    md = "![cover art [1]](images/cover.jpg)"
    protected, images = _protect_markdown_images(md)
    assert images == [md]
    assert _restore_markdown_images(protected, images) == md
