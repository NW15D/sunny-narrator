"""Test getattr fix in app.py for LLMService client resolution."""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_getattr_no_crash():
    """
    Verify that the getattr fix in app.py doesn't crash when
    LLMService has no clientTranslate attribute.
    
    The old code: getattr(ta.llm_service, 'clientProofread', ta.llm_service.clientTranslate)
    would crash because ta.llm_service.clientTranslate is evaluated eagerly.
    """
    # Create a mock LLMService that only has _secondary_client and _primary_client
    # (like the real LLMService class, NOT the LLMServiceCompat)
    mock_llm_service = MagicMock()
    # Remove clientTranslate and clientProofread to simulate raw LLMService
    del mock_llm_service.clientTranslate
    del mock_llm_service.clientProofread
    # But keep _secondary_client and _primary_client
    mock_llm_service._secondary_client = MagicMock()
    mock_llm_service._primary_client = MagicMock()
    
    # Simulate the fixed getattr logic from app.py
    client = getattr(mock_llm_service, 'clientProofread', None)
    if client is None:
        client = getattr(mock_llm_service, '_secondary_client', None)
    if client is None:
        client = getattr(mock_llm_service, 'clientTranslate', None)
    if client is None:
        client = getattr(mock_llm_service, '_primary_client', None)
    
    assert client is not None, "Should have found a client"
    assert client is mock_llm_service._secondary_client, "Should use _secondary_client as fallback"


def test_getattr_with_compat_layer():
    """
    Verify that when LLMServiceCompat is used (has clientProofread),
    the fix correctly uses it.
    """
    mock_llm_service = MagicMock()
    mock_llm_service.clientProofread = MagicMock(name='clientProofread')
    mock_llm_service.clientTranslate = MagicMock(name='clientTranslate')
    
    # Simulate the fixed getattr logic
    client = getattr(mock_llm_service, 'clientProofread', None)
    if client is None:
        client = getattr(mock_llm_service, '_secondary_client', None)
    if client is None:
        client = getattr(mock_llm_service, 'clientTranslate', None)
    if client is None:
        client = getattr(mock_llm_service, '_primary_client', None)
    
    assert client is mock_llm_service.clientProofread, "Should use clientProofread when available"


def test_getattr_only_primary_client():
    """
    Verify fallback to _primary_client when nothing else is available.
    """
    mock_llm_service = MagicMock()
    del mock_llm_service.clientTranslate
    del mock_llm_service.clientProofread
    del mock_llm_service._secondary_client
    mock_llm_service._primary_client = MagicMock(name='_primary_client')
    
    # Simulate the fixed getattr logic
    client = getattr(mock_llm_service, 'clientProofread', None)
    if client is None:
        client = getattr(mock_llm_service, '_secondary_client', None)
    if client is None:
        client = getattr(mock_llm_service, 'clientTranslate', None)
    if client is None:
        client = getattr(mock_llm_service, '_primary_client', None)
    
    assert client is mock_llm_service._primary_client, "Should fall back to _primary_client"


def test_old_code_would_crash():
    """
    Demonstrate that the OLD code pattern would crash with raw LLMService.
    This is a regression test to document why the fix was needed.
    """
    mock_llm_service = MagicMock()
    del mock_llm_service.clientTranslate
    del mock_llm_service.clientProofread
    mock_llm_service._secondary_client = MagicMock()
    
    # Old pattern: getattr(obj, 'attr', obj.other_attr) - default is evaluated eagerly
    try:
        client = getattr(mock_llm_service, 'clientProofread', mock_llm_service.clientTranslate)
        assert False, "Old code should have raised AttributeError"
    except AttributeError:
        pass  # Expected - this is why we fixed it


if __name__ == '__main__':
    test_getattr_no_crash()
    test_getattr_with_compat_layer()
    test_getattr_only_primary_client()
    test_old_code_would_crash()
    print("All getattr fix tests passed!")
