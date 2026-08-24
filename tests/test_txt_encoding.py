"""Tests for TXT encoding detection and XML escaping in txt_handler."""
import os
import tempfile

import pytest

from src.txt_handler import parse_txt


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write_file(path, text, encoding):
    with open(path, 'w', encoding=encoding) as f:
        f.write(text)


def test_utf8_txt_loads(tmp_dir):
    path = os.path.join(tmp_dir, "test.txt")
    content = "Привет, мир! Hello world."
    _write_file(path, content, "utf-8")
    body, header, footer = parse_txt(path)
    assert "Привет, мир!" in body


def test_cp1251_txt_loads(tmp_dir):
    path = os.path.join(tmp_dir, "test_cp1251.txt")
    content = "Тестирование кодировки cp1251."
    _write_file(path, content, "cp1251")
    body, header, footer = parse_txt(path)
    assert "Тестирование" in body


def test_latin1_txt_loads(tmp_dir):
    path = os.path.join(tmp_dir, "test_latin1.txt")
    # latin-1 specific chars: é, ñ, ü
    content = "Caf\xe9 r\xe9sum\xe9 na\xefve"
    with open(path, 'wb') as f:
        f.write(content.encode('latin-1'))
    body, header, footer = parse_txt(path)
    # Should not crash; content should be present (possibly with replacements)
    assert "Caf" in body


def test_title_escaped(tmp_dir):
    path = os.path.join(tmp_dir, "Tom & Jerry.txt")
    _write_file(path, "Some content.", "utf-8")
    body, header, footer = parse_txt(path)
    # The raw '&' must not appear unescaped in the title
    assert "&amp;" in header
    assert "<book-title>Tom &amp; Jerry</book-title>" in header
