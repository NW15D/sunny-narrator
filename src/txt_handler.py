import logging
import os
import re
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

try:
    from charset_normalizer import from_bytes as detect_encoding
except ImportError:
    detect_encoding = None

import src.fb2_handler as fb2

logger = logging.getLogger(__name__)

# Known chapter-marker patterns for common scraped web-novel formats:
# Korean episode markers ("제20화", bare "20화"), and "Chapter N" / "Глава N" /
# "Episode N" headings in English/Russian.
_CHAPTER_MARKER_RE = re.compile(
    r'^\s*('
    r'제\s*\d+\s*화'
    r'|\d+\s*화'
    r'|chapter\s+\d+'
    r'|глава\s+\d+'
    r'|episode\s+\d+'
    r')',
    re.IGNORECASE,
)

# A line made up only of repeated separator characters (====, ----, ****, ####).
_SEPARATOR_LINE_RE = re.compile(r'^\s*([=\-*_#~])\1{2,}\s*$')


def _is_chapter_heading(line, next_line):
    """A line is a chapter heading if it matches a known marker, or if the
    line right after it is a "====" / "----" style separator — a common
    convention in scraped web-novel TXT dumps.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _CHAPTER_MARKER_RE.match(stripped):
        return True
    if next_line is not None and _SEPARATOR_LINE_RE.match(next_line):
        return True
    return False


def _split_into_chapters(content):
    """Splits raw TXT content into a list of (title, body_text) chapters.

    Returns [(None, content)] untouched when no chapter heading is found,
    so plain (non-chaptered) TXT files keep producing a single section.
    """
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    n = len(lines)

    heading_indices = [
        i for i in range(n)
        if _is_chapter_heading(lines[i], lines[i + 1] if i + 1 < n else None)
    ]

    if not heading_indices:
        return [(None, content)]

    chapters = []
    if heading_indices[0] > 0:
        preamble = '\n'.join(lines[:heading_indices[0]]).strip()
        if preamble:
            chapters.append((None, preamble))

    for idx, start in enumerate(heading_indices):
        title = lines[start].strip()
        body_start = start + 1
        if body_start < n and _SEPARATOR_LINE_RE.match(lines[body_start]):
            body_start += 1
        end = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else n
        chapters.append((title, '\n'.join(lines[body_start:end])))

    return chapters


def _split_paragraphs(text):
    """Splits chapter text into paragraphs.

    When the text contains blank-line-separated blocks, each block is one
    paragraph (lines wrapped inside a block stay joined — classic hard-wrapped
    book TXT). Otherwise every non-empty line is its own paragraph, which is
    how most scraped web-novel TXT is formatted (no blank line between
    paragraphs).
    """
    if '\n\n' in text:
        blocks = re.split(r'\n\s*\n+', text)
    else:
        blocks = text.split('\n')
    return [p.strip() for p in blocks if p.strip()]


def _read_with_fallback(file_path):
    """Read a text file trying multiple encodings.

    Fallback chain: utf-8 → charset-normalizer → cp1251 → latin-1 (errors='replace').
    """
    with open(file_path, 'rb') as f:
        raw = f.read()

    # 1. Try UTF-8 (utf-8-sig strips the BOM if present; plain utf-8 decodes the same)
    try:
        return raw.decode('utf-8-sig').lstrip('\ufeff')
    except UnicodeDecodeError:
        logger.debug("UTF-8 decode failed for %s, trying fallbacks", file_path)

    # 2. Try charset-normalizer if available
    if detect_encoding is not None:
        result = detect_encoding(raw).best()
        if result is not None:
            return str(result)

    # 3. Try cp1251 (common for Russian text)
    try:
        return raw.decode('cp1251')
    except UnicodeDecodeError:
        logger.debug("cp1251 decode failed for %s, falling back to latin-1", file_path)

    # 4. Last resort: latin-1 never raises (maps all 256 byte values)
    return raw.decode('latin-1', errors='replace')


def parse_txt(file_path):
    """
    Parses a TXT file and converts it into an FB2-like XML structure.
    Returns body, header, footer.
    """
    try:
        content = _read_with_fallback(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read TXT file: {e}")

    # Create a simple header
    file_name = os.path.basename(file_path)
    title = os.path.splitext(file_name)[0]
    date_str = str(datetime.now().year)
    
    header = f"""<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description>
    <title-info>
        <genre>unknown</genre>
        <author><first-name></first-name><last-name>Unknown</last-name></author>
        <book-title>{xml_escape(title)}</book-title>
        <date>{date_str}</date>
        <lang>en</lang>
    </title-info>
</description>
"""

    # Create body: split into chapters (if any chapter headings are detected),
    # then into paragraphs within each chapter.
    section_blocks = []
    for chapter_title, chapter_text in _split_into_chapters(content):
        section_parts = []
        if chapter_title:
            section_parts.append(f"<title><p>{xml_escape(chapter_title)}</p></title>")
        for p in _split_paragraphs(chapter_text):
            section_parts.append(f"<p>{xml_escape(p)}</p>")
        if section_parts:
            section_blocks.append("<section>\n" + "\n".join(section_parts) + "\n</section>")

    body = "<body>\n" + "\n".join(section_blocks) + "\n</body>"

    footer = "</FictionBook>"
    
    return body, header, footer

def prepare_chunks(body, max_len_chunk):
    """
    Uses the existing FB2 chunking logic.
    
    Need TXT chunking logic with MAX_LEN_CHUNK

    """
    return fb2.prepare_chunks(body, max_len_chunk)

def get_cover_image(header, footer):
    """
    TXT usually doesn't have an embedded cover.
    Returns None.
    """
    return None

def replace_cover_image(header, footer, body, new_content):
    """
    Replacing cover image in TXT (converted to FB2-structure).
    If we want to support it, we could insert the text description into the body.
    """
    # Reuse fb2 logic if we want to allow inserting text description
    return fb2.replace_cover_image(header, footer, body, new_content)
