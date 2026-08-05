"""Tests for robust JSON parsing fixes (Fix #2)."""
import sys
from pathlib import Path

# Add project root to path (works from any worktree or main checkout)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import parse_json_response, _extract_json_brace, _strip_markdown_fences


def test_brace_counting_nested():
    """Brace counting handles nested objects."""
    text = '{"translation": "He said {something} and left."}'
    result, success = parse_json_response(text)
    assert success
    assert result == "He said {something} and left."


def test_brace_counting_escaped_quotes():
    """Handles escaped quotes in JSON values."""
    text = '{"translation": "He said \\"hello\\" to me"}'
    result, success = parse_json_response(text)
    assert success
    assert result == 'He said "hello" to me'


def test_markdown_fence_stripping():
    """Strips markdown code fences around JSON."""
    text = '```json\n{"translation": "Привет мир"}\n```'
    result, success = parse_json_response(text)
    assert success
    assert result == "Привет мир"


def test_markdown_fence_no_lang():
    """Strips plain ``` fences."""
    text = '```\n{"translation": "Test text"}\n```'
    result, success = parse_json_response(text)
    assert success
    assert result == "Test text"


def test_multi_line_json():
    """Handles multi-line JSON."""
    text = '''Here is the translation:
{
    "translation": "This is a multi-line test"
}
Hope it helps!'''
    result, success = parse_json_response(text)
    assert success
    assert result == "This is a multi-line test"


def test_no_json_fallback():
    """Returns text as-is when no JSON present."""
    text = "This is just plain text translation"
    result, success = parse_json_response(text)
    assert not success  # No JSON found
    assert result == "This is just plain text translation"


def test_suggestions_json():
    """Extracts suggestions array from JSON."""
    text = '{"suggestions": ["Fix tense", "Change word X to Y"]}'
    result, success = parse_json_response(text)
    assert success
    assert isinstance(result, list)
    assert len(result) == 2


def test_empty_text():
    """Handles empty input."""
    result, success = parse_json_response("")
    assert not success
    assert result == ""


def test_none_text():
    """Handles None input."""
    result, success = parse_json_response(None)
    assert not success
    assert result == ""


def test_extract_json_brace_no_match():
    """Returns empty string when no JSON found."""
    assert _extract_json_brace("no json here") == ""
    assert _extract_json_brace("") == ""
    assert _extract_json_brace(None) == ""


def test_strip_markdown_fences_no_fence():
    """Passes through text without fences."""
    text = "Just regular text"
    assert _strip_markdown_fences(text) == text


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
