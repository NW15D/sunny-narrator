
import asyncio
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
sys.path.append("/home/neo/AgProjects/sunny-narrator")

import src.utils as utils
from src.config import Config

# Mock Config
utils.config = Config()
utils.config.debug = True

# Mock remove_tags
utils.remove_tags = lambda x: x

# Mock Validator
def mock_validator(source, target):
    # Pass if target is same length as source (simplified for test)
    return len(target) == len(source)

async def test_retry_success():
    print("\n--- Test: Retry Success ---")
    source = "12345"
    
    # Mock func: Fails first 2 times (returns short), succeeds 3rd
    attempts = 0
    async def mock_llm(text, temperature):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return "12" # Fail validation
        return "12345" # Pass

    result = await utils.process_with_retries_and_rechunking(
        mock_llm, source, mock_validator, role="TEST"
    )
    print(f"Result: {result}")
    assert result == "12345"
    assert attempts == 3
    print("PASS")

async def test_rechunking_trigger():
    print("\n--- Test: Rechunking Trigger ---")
    # Make source long enough (>500) to trigger split
    source = "a" * 600
    
    # Mock func: Always fails validation for full text, succeeds for smaller
    async def mock_llm(text, temperature):
        if len(text) > 400:
            return "fail" # validation fails
        return text # validation passes (len==len)

    result = await utils.process_with_retries_and_rechunking(
        mock_llm, source, mock_validator, role="TEST"
    )
    
    # Should have split into ~330 and ~270 (roughly half)
    # And recursively called mock_llm on them, which passed because len < 400
    # Then combined "a"*330 + "a"*270 = source
    print(f"Result len: {len(result)}")
    assert len(result) == 600
    assert result == source
    print("PASS")

async def main():
    await test_retry_success()
    await test_rechunking_trigger()

if __name__ == "__main__":
    asyncio.run(main())
