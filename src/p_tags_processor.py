"""
P-Tags Processing Utility

Handles <p> tag validation and auto-structuring for translated chunks.
"""

import re
from typing import Tuple


def _has_p_tags(text: str) -> Tuple[bool, bool]:
    """
    Check for presence of <p> and </p> tags.
    
    Returns:
        Tuple of (has_open_tag, has_close_tag)
    """
    has_open = '<p>' in text
    has_close = '</p>' in text
    return has_open, has_close


def _count_p_tags(text: str) -> Tuple[int, int]:
    """
    Count <p> and </p> tags in text.
    
    Returns:
        Tuple of (open_count, close_count)
    """
    open_count = text.count('<p>')
    close_count = text.count('</p>')
    return open_count, close_count


def post_process_p_tags(text: str) -> str:
    """
    Process translated chunk to ensure <p> integrity.
    
    Hybrid logic:
    1. If <p> and/or </p> exist → validate balance (equal counts)
    2. If NO <p> tags exist → auto-structure with:
       - <p> prefix
       - \n\n → </p><p> conversion
       - </p> suffix
    
    Args:
        text: Translated chunk content (after remove_tags_with_check)
        
    Returns:
        Processed chunk with valid <p> structure
    """
    # Handle empty/whitespace-only input
    if not text or not text.strip():
        return text
    
    # Check for ANY <p> tags
    has_open, has_close = _has_p_tags(text)
    
    if has_open or has_close:
        # Section A: Validate balance
        open_count, close_count = _count_p_tags(text)
        
        if open_count != close_count:
            # Auto-balance: add missing tags
            if open_count > close_count:
                # Missing closing tags → add at end
                text += '</p>' * (open_count - close_count)
            else:
                # Missing opening tags → add at start
                text = '<p>' * (close_count - open_count) + text
        
        return text
    
    else:
        # Section B: No <p> tags at all → auto-structure
        # 1. Add opening tag
        text = '<p>' + text
        
        # 2. Convert paragraph breaks (\n\n → </p><p>)
        # Note: \n\s*\n handles whitespace between paragraphs
        text = re.sub(r'\n\s*\n', '</p><p>', text)
        
        # 3. Add closing tag
        text += '</p>'
        
        return text
