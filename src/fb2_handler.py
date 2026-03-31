"""
FB2 file handler.

Handles parsing, reading, and writing FB2 files.
Uses xml_utils for common XML operations.
"""

import re
from pathlib import Path
from src.config import Config
from src.xml_utils import (
    extract_metadata,
    update_header_with_metadata,
    get_cover_image,
    replace_cover_image,
    prepare_chunks
)

config = Config()

# Re-export functions for backward compatibility
__all__ = [
    'parse_xml',
    'extract_metadata',
    'update_header_with_metadata',
    'get_cover_image',
    'replace_cover_image',
    'prepare_chunks',
    'save_fb2',
    'add_translator_info'
]


def parse_xml(file_path: str) -> tuple:
    """
    Parses an FB2 XML file and separates the header, body, and footer.
    Also handles cleanup and injection of translator info.
    
    Args:
        file_path: Path to FB2 file
        
    Returns:
        Tuple of (body, header, footer)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
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
        
        # Add translator info
        header = add_translator_info(header)

        # Remove <myheader> and <myfooter> from header and footer
        header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
        footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)

        if config.debug:
            print(f"Body length: {len(body)}")
            
        return body, header, footer


def add_translator_info(header: str) -> str:
    """
    Add translator info to FB2 header.
    
    Args:
        header: FB2 header string
        
    Returns:
        Updated header with translator info
    """
    translator_block = '<translator><nickname>Sunny narrator opensource AI translator</nickname><email>n@uwns.org</email></translator></title-info>'
    header = re.sub(
        r'</title-info>',
        translator_block,
        header,
        flags=re.DOTALL
    )
    return header


def save_fb2(body: str, header: str, footer: str, output_path: str, auto_repair: bool = True) -> None:
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
