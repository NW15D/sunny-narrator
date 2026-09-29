"""
FB2 file handler.

Handles parsing, reading, and writing FB2 files.
Uses xml_utils for common XML operations.
"""

import re
import logging
from pathlib import Path

import chardet

from src.config import Config

logger = logging.getLogger(__name__)
from src.xml_utils import (
    extract_metadata,
    update_header_with_metadata,
    get_cover_image,
    replace_cover_image,
)
from src.fb2_structure import prepare_body_structure

config = Config()

# Re-export functions for backward compatibility
__all__ = [
    'parse_xml',
    'extract_metadata',
    'update_header_with_metadata',
    'get_cover_image',
    'replace_cover_image',
    'prepare_body_structure',
    'save_fb2',
    'add_translator_info'
]


def _read_file_with_encoding_fallback(file_path):
    """Read file trying UTF-8 first, then detect encoding."""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return f.read().lstrip('\ufeff')
    except UnicodeDecodeError:
        logger.debug("UTF-8 decode failed for %s, falling back to encoding detection", file_path)

    with open(file_path, 'rb') as f:
        raw = f.read()
    detected = chardet.detect(raw[:10000])
    encoding = detected.get('encoding', 'windows-1251') or 'windows-1251'
    logger.info(f"Detected encoding '{encoding}' for {file_path}")

    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return raw.decode('windows-1251', errors='replace')


def parse_xml(file_path: str) -> tuple:
    """
    Parses an FB2 XML file and separates the header, body, and footer.
    Also handles cleanup and injection of translator info.
    
    Args:
        file_path: Path to FB2 file
        
    Returns:
        Tuple of (body, header, footer)
    """
    content = _read_file_with_encoding_fallback(file_path)
    start_body = content.find('<body')
    end_body_tag = content.find('</body>')

    if start_body == -1 or end_body_tag == -1:
        raise ValueError("Body tag not found in the XML file")

    # Find the end of the opening <body> tag
    end_start_body = content.find('>', start_body) + 1
    end_body = end_body_tag

    header = content[:start_body]
    body = content[end_start_body:end_body]
    footer = content[end_body_tag + len('</body>'):]

    # Remove namespaces
    body = re.sub(r'\sxmlns="[^"]+"', '', body, count=1)
    body = re.sub(r'<myheader>.*?</myheader>', '', body, flags=re.DOTALL)
    body = re.sub(r'<myfooter>.*?</myfooter>', '', body, flags=re.DOTALL)

    # Output is always written as UTF-8, whatever the source file used
    header = re.sub(r'(<\?xml[^>]*?encoding\s*=\s*)(["\'])[^"\']*\2', r'\1"UTF-8"', header, count=1)

    # Add translator info
    header = add_translator_info(header)

    # Remove <myheader> and <myfooter> from header and footer
    header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
    footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)

    if config.debug:
        print(f"Body length: {len(body)}")

    return body, header, footer


_TRANSLATOR_NICK = 'Sunny narrator opensource AI translator'


def add_translator_info(header: str) -> str:
    """
    Add translator info to FB2 header.

    <translator> has to precede <sequence> inside <title-info> (schema order),
    so it is inserted there rather than blindly before </title-info>.

    Args:
        header: FB2 header string

    Returns:
        Updated header with translator info
    """
    m = re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL)
    if not m or _TRANSLATOR_NICK in m.group(0):
        return header
    section = m.group(0)
    seq = re.search(r'<sequence\b', section)
    pos = seq.start() if seq else section.rindex('</title-info>')
    block = f'<translator><nickname>{_TRANSLATOR_NICK}</nickname><email>n@uwns.org</email></translator>'
    return header[:m.start()] + section[:pos] + block + section[pos:] + header[m.end():]


def save_fb2(body: str, header: str, footer: str, output_path: str, auto_repair: bool = False) -> None:
    """
    Save FB2 file from components.
    
    Args:
        body: FB2 body content
        header: FB2 header
        footer: FB2 footer
        output_path: Output file path
        auto_repair: Whether to auto-repair common XML errors (default: True)
    """
    content = header + body + footer
    
    # Auto-repair FB2 XML if enabled
    if auto_repair:
        from .fb2_repair import repair_and_validate
        import logging
        
        logger = logging.getLogger(__name__)
        repaired, repairs, errors = repair_and_validate(content)
        
        if repairs:
            logger.info(" | ".join(repairs))
            content = repaired
        
        if errors:
            logger.warning(f"FB2 validation errors after repair: {len(errors)}")
            for error in errors[:5]:  # Log first 5 errors
                logger.warning(f"  - {error}")
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)


# Keep existing functions for backward compatibility
# They now delegate to xml_utils
