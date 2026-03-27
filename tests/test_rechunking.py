"""
Tests for rechunking and retry logic in utils.py
"""
import sys
import os
from unittest.mock import MagicMock

# Mock third party modules
sys.modules['openai'] = MagicMock()
sys.modules['tiktoken'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['httpx'] = MagicMock()

# Add project root to sys.path
sys.path.insert(0, "/home/neo/.openclaw/workspace-dev/sunny-narrator")

import src.utils as utils
from src.config import Config

# Mock Config
utils.config = Config()
utils.config.debug = True

# Mock remove_tags
utils.remove_tags = lambda x: x

# Mock tiktoken
def mock_encode(text):
    # Simple mock: 1 char = 1 token
    return list(range(len(text)))

utils.tiktoken.get_encoding = lambda x: type('MockEncoding', (), {'encode': mock_encode})()


def mock_validator(source, target):
    """Pass if target is same length as source (simplified for test)"""
    return len(target) == len(source)


def test_retry_success():
    """Test that retry logic works when function eventually succeeds"""
    print("\n--- Test: Retry Success ---")
    source = "12345"
    
    # Mock func: Fails first 2 times (returns short), succeeds 3rd
    attempts = 0
    def mock_llm(text, temperature):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return "12"  # Fail validation
        return "12345"  # Pass

    result = utils.process_with_retries_and_rechunking(
        mock_llm, source, mock_validator, role="TEST"
    )
    print(f"Result: {result}")
    assert result == "12345", f"Expected '12345', got '{result}'"
    assert attempts == 3, f"Expected 3 attempts, got {attempts}"
    print("PASS")


def test_rechunking_trigger():
    """Test that rechunking is triggered when validation fails for long text"""
    print("\n--- Test: Rechunking Trigger ---")
    # Make source long enough (>500) to trigger split
    source = "a" * 600
    
    # Mock func: Always fails validation for full text, succeeds for smaller
    call_count = [0]
    def mock_llm(text, temperature):
        call_count[0] += 1
        if len(text) > 400:
            return "fail"  # validation fails
        return text  # validation passes (len==len)

    result = utils.process_with_retries_and_rechunking(
        mock_llm, source, mock_validator, role="TEST"
    )
    
    # Should have split into ~330 and ~270 (roughly half)
    # And recursively called mock_llm on them, which passed because len < 400
    # Then combined "a"*330 + "a"*270 = source
    print(f"Result len: {len(result)}")
    print(f"Total LLM calls: {call_count[0]}")
    assert len(result) == 600, f"Expected len 600, got {len(result)}"
    assert result == source, f"Result doesn't match source"
    print("PASS")


def test_fallback_to_source():
    """Test that when all retries fail and text is short, we get last result"""
    print("\n--- Test: Fallback to Source ---")
    source = "short"
    
    def mock_llm(text, temperature):
        return "different"  # Always returns different length

    result = utils.process_with_retries_and_rechunking(
        mock_llm, source, mock_validator, role="TEST"
    )
    
    print(f"Result: {result}")
    # Should return last result since text is too short to split
    assert result == "different", f"Expected 'different', got '{result}'"
    print("PASS")


def test_no_validator():
    """Test that when no validator is provided, first result is returned"""
    print("\n--- Test: No Validator ---")
    source = "any text"
    
    def mock_llm(text, temperature):
        return "translated"

    result = utils.process_with_retries_and_rechunking(
        mock_llm, source, validation_func=None, role="TEST"
    )
    
    print(f"Result: {result}")
    assert result == "translated", f"Expected 'translated', got '{result}'"
    print("PASS")


def main():
    """Run all tests"""
    print("=" * 50)
    print("Running Rechunking Tests")
    print("=" * 50)
    
    try:
        test_retry_success()
        test_rechunking_trigger()
        test_fallback_to_source()
        test_no_validator()
        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("=" * 50)
        return 0
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
