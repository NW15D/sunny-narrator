"""Tests for JSON mode LLM response parsing."""


def test_parse_json_translation():
    """Test parsing simple JSON translation response"""
    from src.utils import parse_json_response
    
    text = '{"translation": "переведенный текст"}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert result == "переведенный текст"


def test_parse_json_with_wrapper():
    """Test parsing JSON with conversational wrapper"""
    from src.utils import parse_json_response
    
    text = 'Here is your translation: {"translation": "text"}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert result == "text"


def test_parse_json_with_prefix_suffix():
    """Test parsing JSON with text before and after"""
    from src.utils import parse_json_response
    
    text = 'Sure, here is the translation: {"translation": "translated text"} Let me know if you need changes.'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert result == "translated text"


def test_parse_json_suggestions():
    """Test parsing JSON suggestions list for reflection stage"""
    from src.utils import parse_json_response
    
    text = '{"suggestions": ["Fix this", "Change that", "Improve style"]}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert isinstance(result, list)
    assert len(result) == 3


def test_parse_invalid_json_returns_original():
    """Test that plain text returns as-is"""
    from src.utils import parse_json_response
    
    text = "Just plain text without JSON"
    result, is_json = parse_json_response(text)
    assert is_json is False
    assert result == "Just plain text without JSON"


def test_parse_empty_json():
    """Test handling of empty JSON response"""
    from src.utils import parse_json_response
    
    text = "{}"
    result, is_json = parse_json_response(text)
    # Empty JSON should return as-is (not valid translation)
    assert is_json is False


def test_parse_malformed_json():
    """Test handling of malformed JSON"""
    from src.utils import parse_json_response
    
    text = '{invalid json'
    result, is_json = parse_json_response(text)
    assert is_json is False


def test_config_json_mode_flag():
    """Test that JSON_MODE flag is read from config"""
    from src.config import Config
    import os
    
    # Save original
    orig = os.environ.get('JSON_MODE')
    
    # Test True
    os.environ['JSON_MODE'] = 'true'
    config = Config()
    assert config.json_mode is True
    
    # Test False
    os.environ['JSON_MODE'] = 'false'
    config = Config()
    assert config.json_mode is False
    
    # Test default
    if orig:
        os.environ['JSON_MODE'] = orig
    else:
        os.environ.pop('JSON_MODE', None)
    
    config = Config()
    assert config.json_mode is False  # default


def test_remove_tags_with_check_json_priority():
    """Test that remove_tags_with_check uses JSON parsing first"""
    from src.utils import remove_tags_with_check, LLMRole
    
    # JSON with translation should be extracted
    text = '{"translation": "тестовый перевод"}'
    result = remove_tags_with_check(text, "test", LLMRole.TRANSLATE)
    assert result == "тестовый перевод"
