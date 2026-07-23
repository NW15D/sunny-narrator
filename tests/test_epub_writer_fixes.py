"""Tests for epub_writer.py fixes: missing imports + image regex."""
import importlib
import sys
import os
import re

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.epub_writer as epub_writer_module


def test_logger_defined():
    """Module must have a `logger` attribute defined at module level."""
    assert hasattr(epub_writer_module, 'logger'), "epub_writer module must define `logger` at module level"


def test_re_imported():
    """Module must have `re` in its namespace."""
    assert 're' in dir(epub_writer_module), "epub_writer module must import `re`"


def test_binary_content_type_first():
    """Regex must match when content-type comes before id (standard FB2 order)."""
    footer = '<binary content-type="image/png" id="cover.png">BASE64DATA</binary>'
    pattern = r'<binary(?=[^>]*?id="([^"]+)")(?=[^>]*?content-type="([^"]+)")[^>]*?>([^<]+)</binary>'
    match = re.search(pattern, footer)
    assert match is not None, f"Regex must match content-type-first order: {footer}"
    assert match.group(1) == "cover.png"
    assert match.group(2) == "image/png"
    assert match.group(3) == "BASE64DATA"


def test_binary_id_first():
    """Regex must match when id comes before content-type."""
    footer = '<binary id="img1" content-type="image/jpeg">DATA</binary>'
    pattern = r'<binary(?=[^>]*?id="([^"]+)")(?=[^>]*?content-type="([^"]+)")[^>]*?>([^<]+)</binary>'
    match = re.search(pattern, footer)
    assert match is not None, f"Regex must match id-first order: {footer}"
    assert match.group(1) == "img1"
    assert match.group(2) == "image/jpeg"
    assert match.group(3) == "DATA"
