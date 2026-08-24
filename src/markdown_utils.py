"""Markdown utilities for processing and generating markdown content."""
import os
import re
from typing import List, Union
from bs4 import BeautifulSoup

# Precompiled patterns for Calibre-specific cleanup (narrowed to avoid removing valid Pandoc attributes)
_RE_CALIBRE_COMMENT = re.compile(r'<!--\s*\d+\s*-->')
_RE_CALIBRE_ANCHOR = re.compile(r'\{#calibre[^}]*\}')  # Only calibre-specific anchors
_RE_CALIBRE_CLASS = re.compile(r'\{\.calibre\d*\}')  # Only calibre-specific classes

# Precompiled heading extraction pattern
_RE_HEADING = re.compile(r'^(#{1,6})\s+(.+)$')


def parse_structural_blocks(content: str) -> List[tuple]:
    """
    Parse markdown into structural blocks that should not be split.

    Returns list of (text, block_type) tuples where block_type is one of:
    'heading', 'code_block', 'table', 'list', 'blockquote', 'image', 'paragraph'

    Adapted from deusyu/translate-book (scripts/convert.py) to prevent
    splitting markdown syntax (fences, list markers, table rows, blockquote
    prefixes) across chunk boundaries.
    """
    blocks = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code block (fenced)
        if stripped.startswith('```'):
            block_lines = [line]
            i += 1
            while i < len(lines):
                block_lines.append(lines[i])
                if lines[i].strip().startswith('```') and len(block_lines) > 1:
                    i += 1
                    break
                i += 1
            blocks.append(('\n'.join(block_lines), 'code_block'))
            continue

        # Heading
        if re.match(r'^#{1,6}\s', stripped):
            blocks.append((line, 'heading'))
            i += 1
            continue

        # Blockquote
        if stripped.startswith('>'):
            block_lines = [line]
            i += 1
            while i < len(lines) and (lines[i].strip().startswith('>') or
                                       (lines[i].strip() and not re.match(r'^#{1,6}\s', lines[i].strip())
                                        and not lines[i].strip().startswith('```')
                                        and not lines[i].strip().startswith('|')
                                        and not re.match(r'^[-*+]\s', lines[i].strip())
                                        and not re.match(r'^\d+\.\s', lines[i].strip())
                                        and block_lines[-1].strip().startswith('>'))):
                block_lines.append(lines[i])
                i += 1
            blocks.append(('\n'.join(block_lines), 'blockquote'))
            continue

        # Table (lines starting with |)
        if stripped.startswith('|'):
            block_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                block_lines.append(lines[i])
                i += 1
            blocks.append(('\n'.join(block_lines), 'table'))
            continue

        # List (unordered or ordered)
        if re.match(r'^[-*+]\s', stripped) or re.match(r'^\d+\.\s', stripped):
            block_lines = [line]
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                # Continue list: list items, indented continuation, or blank lines within list
                if (re.match(r'^[-*+]\s', s) or re.match(r'^\d+\.\s', s) or
                        (lines[i].startswith('  ') and s) or
                        (s == '' and i + 1 < len(lines) and
                         (re.match(r'^[-*+]\s', lines[i+1].strip()) or
                          re.match(r'^\d+\.\s', lines[i+1].strip()) or
                          lines[i+1].startswith('  ')))):
                    block_lines.append(lines[i])
                    i += 1
                else:
                    break
            blocks.append(('\n'.join(block_lines), 'list'))
            continue

        # Image line (standalone or with surrounding caption)
        if re.match(r'!\[', stripped):
            blocks.append((line, 'image'))
            i += 1
            continue

        # Empty line — just a paragraph separator
        if stripped == '':
            blocks.append((line, 'paragraph'))
            i += 1
            continue

        # Regular paragraph — collect contiguous non-empty, non-special lines
        block_lines = [line]
        i += 1
        while i < len(lines):
            s = lines[i].strip()
            if (s == '' or s.startswith('```') or re.match(r'^#{1,6}\s', s) or
                    s.startswith('>') or s.startswith('|') or
                    re.match(r'^[-*+]\s', s) or re.match(r'^\d+\.\s', s) or
                    re.match(r'!\[', s)):
                break
            block_lines.append(lines[i])
            i += 1
        blocks.append(('\n'.join(block_lines), 'paragraph'))
        continue

    return blocks


def merge_blocks_to_chunks(blocks: List[tuple], target_size: int = 6000) -> List[str]:
    """
    Merge structural blocks into chunks respecting target_size.

    Prefers to split at heading boundaries. Never splits within a single
    structural block unless the block itself exceeds target_size * 1.5.
    """
    chunks = []
    current_parts = []
    current_size = 0

    def flush():
        nonlocal current_parts, current_size
        if current_parts:
            chunks.append('\n'.join(current_parts))
            current_parts = []
            current_size = 0

    for text, btype in blocks:
        block_size = len(text)

        # If a single block is oversized, handle degradation
        if block_size > target_size * 1.5:
            flush()
            sub_chunks = _force_split_block(text, target_size)
            chunks.extend(sub_chunks)
            continue

        # Prefer to split at heading boundaries
        if btype == 'heading' and current_size > 0:
            flush()

        # Would adding this block exceed target?
        if current_size + block_size > target_size and current_parts:
            flush()

        current_parts.append(text)
        current_size += block_size

    flush()
    return chunks


def _force_split_block(text: str, target_size: int) -> List[str]:
    """
    Force-split an oversized block by paragraph (empty lines), then by lines.

    For fenced code blocks, each resulting chunk gets proper opening/closing fences
    so it remains valid Markdown.
    """
    stripped = text.strip()
    is_fenced_code = stripped.startswith('```')

    # Extract fence info for code blocks
    fence_opener = ''
    if is_fenced_code:
        first_line = stripped.split('\n', 1)[0]
        fence_opener = first_line  # e.g. "```python"

    # Try splitting by empty lines first (not applicable for code blocks — no empty lines expected)
    if not is_fenced_code:
        paragraphs = re.split(r'\n\n+', text)
        if len(paragraphs) > 1:
            chunks = []
            current = []
            current_size = 0
            for para in paragraphs:
                para_size = len(para)
                if current_size + para_size > target_size and current:
                    chunks.append('\n\n'.join(current))
                    current = [para]
                    current_size = para_size
                else:
                    current.append(para)
                    current_size += para_size
            if current:
                chunks.append('\n\n'.join(current))
            return chunks

    # Split by lines
    lines = text.split('\n')

    # For code blocks, strip the opening and closing fences before splitting content
    if is_fenced_code:
        # Remove opening fence line
        content_lines = lines[1:]
        # Remove closing fence line if present
        if content_lines and content_lines[-1].strip().startswith('```'):
            content_lines = content_lines[:-1]
        lines = content_lines

    chunks = []
    current = []
    current_size = 0
    for line in lines:
        line_size = len(line) + 1
        if current_size + line_size > target_size and current:
            chunks.append('\n'.join(current))
            current = [line]
            current_size = line_size
        else:
            current.append(line)
            current_size += line_size
    if current:
        chunks.append('\n'.join(current))

    # Re-wrap each chunk in fences for code blocks
    if is_fenced_code:
        chunks = [f"{fence_opener}\n{chunk}\n```" for chunk in chunks]

    return chunks


def split_markdown_structured(text: str, target_size: int = 6000) -> List[str]:
    """
    Split markdown into structural chunks that never break markdown syntax.

    Uses parse_structural_blocks + merge_blocks_to_chunks so that fences,
    list markers, table rows and blockquote prefixes stay intact within a chunk.
    """
    if not text or not text.strip():
        return []
    if len(text.strip()) <= target_size:
        return [text]
    blocks = parse_structural_blocks(text)
    return merge_blocks_to_chunks(blocks, target_size)


def split_markdown_by_size(text: str, target_size: int = 4000) -> List[str]:
    """
    Split markdown text into chunks of approximately target_size characters.
    
    Args:
        text: Markdown text to split
        target_size: Target size for each chunk in characters
        
    Returns:
        List of markdown text chunks
    """
    if len(text) <= target_size:
        return [text]
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    # Split by paragraphs/sections
    sections = re.split(r'\n\s*\n', text)
    
    for section in sections:
        section_size = len(section)
        
        if current_size + section_size > target_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = []
            current_size = 0
        
        current_chunk.append(section)
        current_size += section_size
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks if chunks else [text]


def extract_headings(content: Union[str, BeautifulSoup]) -> List[dict]:
    """
    Extract headings from markdown text or HTML.
    
    Args:
        content: Markdown text (str) or BeautifulSoup object (HTML)
        
    Returns:
        List of heading dicts with level, text, and id
    """
    headings = []
    
    # Handle BeautifulSoup/HTML input
    if hasattr(content, 'find_all'):  # BeautifulSoup object
        html_headings = content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for h in html_headings:
            level = int(h.name[1])  # h1 -> 1, h2 -> 2, etc.
            text = h.get_text().strip()
            heading_id = generate_heading_id(text, headings)
            headings.append({
                'level': level,
                'text': text,
                'id': heading_id
            })
        return headings
    
    # Handle markdown text input
    for line in content.split('\n'):
        match = _RE_HEADING.match(line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            heading_id = generate_heading_id(text, headings)
            headings.append({
                'level': level,
                'text': text,
                'id': heading_id
            })
    
    return headings


def generate_heading_id(text: str, existing_headings: List[dict] = None) -> str:
    """
    Generate a unique heading ID from heading text.
    
    Args:
        text: Heading text
        existing_headings: List of existing headings to ensure uniqueness
        
    Returns:
        URL-safe heading ID
    """
    # Convert to lowercase, replace spaces with hyphens.
    # Use Unicode-aware case folding (locale-agnostic) so non-English
    # headings (Cyrillic, German umlauts, etc.) get stable URL-safe IDs
    # instead of being stripped to empty strings by ASCII \w matching.
    heading_id = text.casefold()
    heading_id = re.sub(r'[^\w\s-]', '', heading_id, flags=re.UNICODE)
    heading_id = re.sub(r'\s+', '-', heading_id)
    heading_id = re.sub(r'-+', '-', heading_id)
    heading_id = heading_id.strip('-')
    
    # Fallback for headings that produced no safe characters (e.g. emoji-only)
    if not heading_id:
        heading_id = 'heading'
    
    # Ensure uniqueness
    if existing_headings:
        counter = 1
        base_id = heading_id
        while any(h['id'] == heading_id for h in existing_headings):
            heading_id = f"{base_id}-{counter}"
            counter += 1
    
    return heading_id


def generate_toc_html(headings: List[dict], min_level: int = 1) -> str:
    """
    Generate HTML table of contents from headings.
    
    Args:
        headings: List of heading dicts
        min_level: Minimum heading level to include
        
    Returns:
        HTML table of contents
    """
    filtered = [h for h in headings if h['level'] >= min_level]
    
    if not filtered:
        return '<nav class="toc"></nav>'
    
    html = ['<nav class="toc">', '<ul>']
    
    for heading in filtered:
        indent = '  ' * (heading['level'] - min_level)
        html.append(f'{indent}<li><a href="#{heading["id"]}">{heading["text"]}</a></li>')
    
    html.append('</ul>')
    html.append('</nav>')
    
    return '\n'.join(html)


def sanitize_surrogates(text: str) -> str:
    """
    Remove surrogate code points (U+D800-U+DFFF) from a string.

    Surrogates can appear when pypandoc/calibre processes broken EPUBs
    with invalid UTF-8 bytes. They cause UnicodeEncodeError on encoding.

    Args:
        text: Input string potentially containing surrogates

    Returns:
        String with all surrogate code points replaced by U+FFFD (replacement char)
    """
    if not text:  # handles None, empty string quickly
        return text
    return re.sub(r'[\ud800-\udfff]', '\ufffd', text)


def clean_markdown_content(text: str) -> str:
    """
    Clean markdown content by removing extra whitespace and normalizing.
    
    Args:
        text: Markdown text to clean
        
    Returns:
        Cleaned markdown text
    """
    # Remove trailing whitespace from each line
    lines = [line.rstrip() for line in text.split('\n')]
    
    # Remove multiple consecutive blank lines
    text = '\n'.join(lines)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    

    # Remove surrogate code points that may leak from broken EPUB parsing
    text = sanitize_surrogates(text)
    return text.strip()


def copy_images_to_output(source_dir: str, output_dir: str) -> List[str]:
    """
    Copy images from source directory to output directory.
    
    Args:
        source_dir: Source directory containing images/ subdirectory
        output_dir: Output directory for copied images
        
    Returns:
        List of copied image filenames
    """
    import shutil
    
    images_dir = os.path.join(source_dir, 'images')
    if not os.path.exists(images_dir):
        return []
    
    os.makedirs(output_dir, exist_ok=True)
    
    copied = []
    for filename in os.listdir(images_dir):
        src_path = os.path.join(images_dir, filename)
        if os.path.isfile(src_path):
            dst_path = os.path.join(output_dir, filename)
            shutil.copy2(src_path, dst_path)
            copied.append(filename)
    
    return copied


def clean_calibre_markers(text: str) -> str:
    """
    Remove Calibre-specific markers from text.
    
    Removes:
    - HTML comments like <!-- 1 -->
    - Calibre anchors like {#calibre_link-1 .calibre1}
    - Calibre classes like {.calibre1}
    
    Preserves user-defined anchors {#my-anchor}, classes {.custom}, key-values.
    
    Args:
        text: Text containing Calibre markers
        
    Returns:
        Cleaned text
    """
    # Remove HTML comments with numbers
    text = _RE_CALIBRE_COMMENT.sub('', text)
    
    # Remove Calibre anchors {#calibre...} only (preserves user-defined anchors)
    text = _RE_CALIBRE_ANCHOR.sub('', text)
    
    # Remove Calibre classes {.calibre} and {.calibreN} only (preserves user-defined classes)
    text = _RE_CALIBRE_CLASS.sub('', text)
    
    return text
