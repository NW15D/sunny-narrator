"""
FB2 file handler.

Handles parsing and reading FB2 files.
Uses xml_utils for common XML operations.
"""

import re
import logging

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
    'add_translator_info',
    'add_annotation_credit'
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
    Also handles cleanup and injection of the translator credit
    (the <translator> block and the one-line annotation credit).
    
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
    # Credit line as the last annotation paragraph (always on, issue #65)
    header = add_annotation_credit(header)

    # Remove <myheader> and <myfooter> from header and footer
    header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
    footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)

    if config.debug:
        print(f"Body length: {len(body)}")

    return body, header, footer


_TRANSLATOR_NICK = 'Sunny narrator opensource AI translator'


def add_translator_info(header: str) -> str:
    """
    Add (or upgrade) translator info in the FB2 header.

    <translator> has to precede <sequence> inside <title-info> (schema order),
    so it is inserted there rather than blindly before </title-info>.

    Idempotent: re-runs never duplicate the block or its <home-page>. Blocks
    written by earlier versions (nickname + <email>n@uwns.org</email>, no
    <home-page>) are upgraded in place so re-converting an old book picks up
    the current credit.

    Args:
        header: FB2 header string

    Returns:
        Updated header with translator info
    """
    from src.utils import GITHUB_URL

    m = re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL)
    if not m:
        return header
    section = m.group(0)

    block_m = next((c for c in re.finditer(r'<translator\b.*?</translator>', section,
                                          flags=re.DOTALL)
                    if _TRANSLATOR_NICK in c.group(0)), None)
    if block_m:
        # Our block exists; normalize it (drop legacy email, single home-page).
        block = block_m.group(0)
        new_block = re.sub(r'<email\b[^>]*>[^<]*</email>', '', block)
        new_block = re.sub(r'<home-page\b[^>]*>[^<]*</home-page>', '', new_block)
        nick = re.search(r'</nickname\s*>|<nickname\s*/>', new_block)
        pos = nick.end() if nick else new_block.index('>') + 1
        new_block = (new_block[:pos]
                     + f'<home-page>{GITHUB_URL}</home-page>'
                     + new_block[pos:])
        if new_block == block:
            return header  # already up to date
        return (header[:m.start()] + section[:block_m.start()] + new_block
                + section[block_m.end():] + header[m.end():])

    seq = re.search(r'<sequence\b', section)
    pos = seq.start() if seq else section.rindex('</title-info>')
    block = (f'<translator><nickname>{_TRANSLATOR_NICK}</nickname>'
             f'<home-page>{GITHUB_URL}</home-page></translator>')
    return header[:m.start()] + section[:pos] + block + section[pos:] + header[m.end():]


def add_annotation_credit(header: str) -> str:
    """
    Add the always-on credit line as the last <p> inside <annotation>.

    Only <annotation> in <title-info> is touched. A book without an
    annotation gets no credit line (no annotation is forced in); a book that
    already carries the credit keeps exactly one copy, so re-parsing the same
    file is idempotent.

    Args:
        header: FB2 header string

    Returns:
        Updated header with the credit line (or the header unchanged)
    """
    from src.utils import CREDIT_LINE, GITHUB_URL

    m = re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL)
    if not m:
        return header
    section = m.group(0)
    am = re.search(r'<annotation\b.*?</annotation>', section, flags=re.DOTALL)
    if not am:
        return header  # no annotation - do not force one in
    annotation = am.group(0)
    if GITHUB_URL in annotation:
        return header  # credit already present - keep it single
    end = annotation.rindex('</annotation>')
    new_annotation = annotation[:end] + f'<p>{CREDIT_LINE}</p>' + annotation[end:]
    return (header[:m.start()] + section[:am.start()] + new_annotation
            + section[am.end():] + header[m.end():])
