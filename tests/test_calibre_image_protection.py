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
