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
from src.fb2_structure import mask_comments, prepare_body_structure

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
    'add_annotation_credit',
    'add_credit'
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
        content = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        content = raw.decode('windows-1251', errors='replace')

    replacement_count = content.count('\ufffd')
    if replacement_count:
        logger.warning(f"File {file_path}: {replacement_count} character(s) could not be decoded "
                       f"as '{encoding}' and were replaced with U+FFFD; the book text may be damaged")
    return content


def parse_xml(file_path: str) -> tuple:
    """
    Parses an FB2 XML file and separates the header, body, and footer.
    Also handles cleanup. The translator credit is added when the translated
    book is written (add_credit), not here: the header goes to the metadata
    translation first.
    
    Args:
        file_path: Path to FB2 file
        
    Returns:
        Tuple of (body, header, footer)
    """
    content = _read_file_with_encoding_fallback(file_path)
    # The tag search runs on a copy with comment bodies blanked out
    # (same length): a '<!-- <body> -->' trap must not cut the book apart.
    masked = mask_comments(content)
    start_body = masked.find('<body')
    end_body_tag = masked.find('</body>')

    if start_body == -1 or end_body_tag == -1:
        raise ValueError("Body tag not found in the XML file")

    body_count = len(re.findall(r'<body\b', masked))
    if body_count > 1:
        logger.warning(f"File {file_path} has {body_count} <body> elements; only the first is "
                       f"translated, the rest (e.g. a notes body) go to the footer as is")

    # Find the end of the opening <body> tag
    end_start_body = content.find('>', start_body) + 1
    end_body = end_body_tag

    header = content[:start_body]
    body = content[end_start_body:end_body]
    footer = content[end_body_tag + len('</body>'):]

    # Remove namespaces
    # DEF-N36: strip every xmlns in the body fragment (nested elements can
    # carry their own); count=1 left a later one -> namespace mismatch.
    body = re.sub(r'\sxmlns="[^"]+"', '', body)
    body = re.sub(r'<myheader>.*?</myheader>', '', body, flags=re.DOTALL)
    body = re.sub(r'<myfooter>.*?</myfooter>', '', body, flags=re.DOTALL)

    # Output is always written as UTF-8, whatever the source file used
    header = re.sub(r'(<\?xml[^>]*?encoding\s*=\s*)(["\'])[^"\']*\2', r'\1"UTF-8"', header, count=1)

    # Remove <myheader> and <myfooter> from header and footer
    header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
    footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)

    if config.debug:
        print(f"Body length: {len(body)}")

    return body, header, footer


# The nickname of the <translator> block before the credit became one text
_LEGACY_NICK = 'Sunny narrator opensource AI translator'


def add_credit(header: str) -> str:
    """The credit of a translated book (src.utils, issue #65): the
    <translator> block and the last annotation paragraph. Called when the
    book is written, after the metadata translation - the LLM never sees it.
    Idempotent: a book translated before keeps one credit, in its current
    wording."""
    return add_annotation_credit(add_translator_info(header))


def add_translator_info(header: str) -> str:
    """
    Add (or update) our <translator> block in the FB2 header: the nickname
    and the repository as <home-page>.

    <translator> has to precede <sequence> inside <title-info> (schema order),
    so it is inserted there rather than blindly before </title-info>.
    Idempotent: a block of an earlier version (the old nickname, an <email>,
    no <home-page>) is rewritten in place; another translator's is left alone.

    Args:
        header: FB2 header string

    Returns:
        Updated header with translator info
    """
    from src.utils import CREDIT_NAME, GITHUB_URL

    m = re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL)
    if not m:
        return header
    section = m.group(0)
    block = (f'<translator><nickname>{CREDIT_NAME}</nickname>'
             f'<home-page>{GITHUB_URL}</home-page></translator>')
    ours = next((c for c in re.finditer(r'<translator\b.*?</translator>', section, flags=re.DOTALL)
                 if _LEGACY_NICK in c.group(0) or GITHUB_URL in c.group(0)), None)
    if ours:
        if ours.group(0) == block:
            return header  # already up to date
        return (header[:m.start()] + section[:ours.start()] + block
                + section[ours.end():] + header[m.end():])
    seq = re.search(r'<sequence\b', section)
    pos = seq.start() if seq else section.rindex('</title-info>')
    return header[:m.start()] + section[:pos] + block + section[pos:] + header[m.end():]


def add_annotation_credit(header: str) -> str:
    """
    The credit as the last <p> of the <annotation> in <title-info>, exactly
    once: a credit paragraph of an earlier run (in any wording - it may have
    been translated) is replaced. A book without an annotation gets one,
    right after <book-title> (schema order), holding the credit alone.

    Args:
        header: FB2 header string

    Returns:
        Updated header with the credit line
    """
    from src.utils import CREDIT_LINE, is_credit_line

    m = re.search(r'<title-info\b.*?</title-info>', header, flags=re.DOTALL)
    if not m:
        return header
    section = m.group(0)
    credit = f'<p>{CREDIT_LINE}</p>'
    am = re.search(r'<annotation\b.*?</annotation>', section, flags=re.DOTALL)
    if am:
        # DEF-N41: an earlier run's credit can only be the trailing
        # paragraph (we always append it last). Drop just that one; a
        # mid-annotation paragraph whose text happens to equal the
        # credit line stays untouched.
        annotation = am.group(0)
        paras = list(re.finditer(r'\s*<p\b[^>]*>(.*?)</p>', annotation, flags=re.DOTALL))
        if paras:
            last = paras[-1]
            if is_credit_line(re.sub(r'<[^>]+>', '', last.group(1))):
                annotation = annotation[:last.start()] + annotation[last.end():]
        end = annotation.rindex('</annotation>')
        new_section = section[:am.start()] + annotation[:end] + credit + annotation[end:] + section[am.end():]
    else:
        title = re.search(r'</book-title\s*>', section)
        if not title:
            return header
        new_section = section[:title.end()] + f'<annotation>{credit}</annotation>' + section[title.end():]
    return header[:m.start()] + new_section + header[m.end():]
