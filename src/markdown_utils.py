"""Markdown chunking for the Calibre pipeline: structure-aware splitting into
translation chunks and surrogate cleanup."""
import re
from typing import List


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


# The prefix of a quote line ("> > ") or of a list item ("- ", "12. ")
_BLOCK_PREFIX = re.compile(r'^((?:>[ \t]?)+)|^[ \t]*(?:[-*+]|\d+[.)])[ \t]+')
# A sentence end with its closing quotes or brackets, then the space after it
_SENTENCE_END = re.compile(r'[.!?\u2026][\u00bb\u201d\u2019"\')\]]*(?=\s)|[\u3002\uff01\uff1f][\u300d\u300f\u201d\uff09]*')


def _split_long_line(line: str, target_size: int) -> List[str]:
    """A line longer than target_size as pieces of at most about target_size,
    cut after sentence ends (a sentence longer than that stays whole); only
    the spaces at a cut are dropped."""
    if len(line) <= target_size:
        return [line]
    # the sentences with the spaces before them, so a piece keeps the text as is
    sentences, start = [], 0
    for m in _SENTENCE_END.finditer(line):
        sentences.append(line[start:m.end()])
        start = m.end()
    sentences.append(line[start:])
    pieces, current = [], ''
    for sentence in sentences:
        if current.strip() and len(current) + len(sentence) > target_size:
            pieces.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        pieces.append(current.strip())
    # the next pieces of a quote stay in the quote, of a list item in the item
    # (pandoc wrote the "> " on every wrapped line before --wrap=none)
    m = _BLOCK_PREFIX.match(line)
    if m and len(pieces) > 1:
        cont = m.group(1) if m.group(1) else ' ' * len(m.group(0))
        pieces = [pieces[0]] + [cont + piece for piece in pieces[1:]]
    return pieces


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

    if not is_fenced_code:
        # a paragraph is one line (pandoc --wrap=none): one longer than a
        # chunk is cut at sentence ends, its pieces joined back with a space
        lines = [piece for line in lines for piece in _split_long_line(line, target_size)]

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


def _fix_heading_hashes(line: str) -> str:
    """Insert a space after leading hashes when a letter follows them
    ('#Head'); '#1' or '#!' are not headings."""
    n = 0
    while n < len(line) and line[n] == '#':
        n += 1
    # only before a letter: "#1 bestseller", "#!/bin/sh" stay as they are
    if 1 <= n <= 6 and n < len(line) and line[n].isalpha():
        return line[:n] + ' ' + line[n:]
    return line


def _is_heading_line(line: str) -> bool:
    """True when the line is an ATX heading with text (1-6 hashes, then a space
    or a tab): the same rule as calibre_pipeline.count_markdown_headings."""
    n = 0
    while n < len(line) and line[n] == '#':
        n += 1
    if n == 0 or n > 6:
        return False
    rest = line[n:]
    return rest.strip() != '' and rest[0] in ' \t'


def normalize_markdown_headings(text: str) -> str:
    """
    Normalize markdown headings so pandoc always recognises them.

    LLM output occasionally contains headings glued to the previous
    paragraph or missing the space after the hashes ('#Chapter 2').
    Pandoc then treats the '#' as literal visible text, and toc.ncx ends
    up empty. This function fixes both cases:

    (a) a space is inserted after leading hashes when the next character
        is a letter (of any script);
    (b) a heading line with no blank line before it gets one inserted.

    '#' characters that are not at the start of a line, lines inside fenced
    code blocks (``` or ~~~) and '#1', '#!' are left untouched. A line that
    starts with a '#hashtag' is read as a heading: Markdown cannot tell them
    apart. The function is idempotent:
    f(f(x)) == f(x).

    Purely structural and alphabet-agnostic: no language-specific patterns
    (no matching on 'Глава'/'Chapter' etc.), so it works for Cyrillic,
    Latin, CJK, Arabic and any other script. It needs no source_lang /
    target_lang input for the same reason.

    Args:
        text: Markdown source.

    Returns:
        Normalized markdown text.
    """
    if not text:
        return text

    lines = text.split('\n')
    out = []
    fence = ''
    for line in lines:
        marker = line.lstrip()[:3]
        if marker in ('```', '~~~'):
            fence = '' if fence == marker else (fence or marker)
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        line = _fix_heading_hashes(line)
        if out and out[-1] != '' and _is_heading_line(line):
            out.append('')
        out.append(line)
    return '\n'.join(out)


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


