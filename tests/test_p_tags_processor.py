"""
Tests for p_tags_processor module.

Tests <p> tag validation and auto-structuring logic.
"""

import pytest
from src.p_tags_processor import post_process_p_tags, _has_p_tags, _count_p_tags


class TestHasPTags:
    """Tests for _has_p_tags helper function."""
    
    def test_both_tags_present(self):
        """Test when both <p> and </p> are present."""
        text = "<p>Hello</p>"
        has_open, has_close = _has_p_tags(text)
        assert has_open is True
        assert has_close is True
    
    def test_only_open_tag(self):
        """Test when only <p> is present."""
        text = "<p>Hello"
        has_open, has_close = _has_p_tags(text)
        assert has_open is True
        assert has_close is False
    
    def test_only_close_tag(self):
        """Test when only </p> is present."""
        text = "Hello</p>"
        has_open, has_close = _has_p_tags(text)
        assert has_open is False
        assert has_close is True
    
    def test_no_tags(self):
        """Test when no <p> tags present."""
        text = "Hello world"
        has_open, has_close = _has_p_tags(text)
        assert has_open is False
        assert has_close is False


class TestCountPTags:
    """Tests for _count_p_tags helper function."""
    
    def test_balanced_single(self):
        """Test balanced single pair."""
        text = "<p>Hello</p>"
        opens, closes = _count_p_tags(text)
        assert opens == 1
        assert closes == 1
    
    def test_balanced_multiple(self):
        """Test balanced multiple pairs."""
        text = "<p>First</p><p>Second</p>"
        opens, closes = _count_p_tags(text)
        assert opens == 2
        assert closes == 2
    
    def test_unbalanced_open(self):
        """Test more open tags than close."""
        text = "<p>Open<p>Open"
        opens, closes = _count_p_tags(text)
        assert opens == 2
        assert closes == 0
    
    def test_unbalanced_close(self):
        """Test more close tags than open."""
        text = "</p><p>Text</p></p>"
        opens, closes = _count_p_tags(text)
        assert opens == 1
        assert closes == 3
    
    def test_no_tags(self):
        """Test text with no tags."""
        text = "Plain text"
        opens, closes = _count_p_tags(text)
        assert opens == 0
        assert closes == 0


class TestPostProcessPTags:
    """Tests for post_process_p_tags main function."""
    
    def test_no_tags_added_structure(self):
        """Test auto-structure when no <p> tags present."""
        text = "First paragraph.\n\nSecond paragraph."
        result = post_process_p_tags(text)
        
        assert result.startswith('<p>'), "Should start with <p>"
        assert result.endswith('</p>'), "Should end with </p>"
        assert '</p><p>' in result, "Should have </p><p> between paragraphs"
    
    def test_balanced_tags_unchanged(self):
        """Test that balanced tags pass through unchanged."""
        text = "<p>Translated text.</p>"
        result = post_process_p_tags(text)
        
        assert result == "<p>Translated text.</p>"
    
    def test_balanced_multiple_unchanged(self):
        """Test multiple balanced pairs unchanged."""
        text = "<p>First</p><p>Second</p>"
        result = post_process_p_tags(text)
        
        assert result == "<p>First</p><p>Second</p>"
    
    def test_missing_closing_tags_auto_fix(self):
        """Test auto-fix for unbalanced tags (missing close)."""
        text = "<p>Open but no close<p>Another open"
        result = post_process_p_tags(text)
        
        assert result == "<p>Open but no close<p>Another open</p></p>"
    
    def test_missing_opening_tags_auto_fix(self):
        """Test auto-fix for missing opening tags."""
        text = "No opening</p><p>Opening missing</p>"
        result = post_process_p_tags(text)
        
        assert result.startswith('<p>')
    
    def test_mixed_content_preserved(self):
        """Test that other XML tags remain intact."""
        text = "<p>Text with <strong>bold</strong> inside.</p>"
        result = post_process_p_tags(text)
        
        assert "<strong>" in result
        assert "</strong>" in result
    
    def test_empty_string_input(self):
        """Test empty string input."""
        text = ""
        result = post_process_p_tags(text)
        
        assert result == ""
    
    def test_whitespace_only_input(self):
        """Test whitespace-only input."""
        text = "   \n  \t  "
        result = post_process_p_tags(text)
        
        assert result == "   \n  \t  "
    
    def test_single_newline_preserved(self):
        """Test that single \n is preserved (not converted to </p><p>)."""
        text = "Line 1\nLine 2"
        result = post_process_p_tags(text)
        
        assert "<p>" in result
        assert result == "<p>Line 1\nLine 2</p>"  # Single \n NOT converted
    
    def test_paragraph_with_whitespace(self):
        """Test \n\s*\n pattern for paragraphs with whitespace."""
        text = "First paragraph.\n\n   \n\nSecond paragraph."
        result = post_process_p_tags(text)
        
        assert '<p>First paragraph.</p>' in result
        assert '<p>Second paragraph.</p>' in result
    
    def test_nested_tags(self):
        """Test nested <p> inside other tags."""
        text = "<subtitle><p>Text</p></subtitle>"
        result = post_process_p_tags(text)
        
        assert "<subtitle>" in result
        assert "<p>" in result
        assert "</p>" in result
        assert "</subtitle>" in result
    
    def test_already_structured_noop(self):
        """Test that already structured text returns unchanged."""
        text = "<p>Already structured.</p>"
        result = post_process_p_tags(text)
        
        assert result == text
        assert result.count('<p>') == 1
        assert result.count('</p>') == 1
