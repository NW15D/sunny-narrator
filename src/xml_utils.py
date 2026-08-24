"""
XML/FB2 utility functions.

Common utilities for XML parsing, metadata extraction, and FB2 manipulation.
Used by fb2_handler, epub_handler, txt_handler.
"""

import re
import os
import tempfile
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Tuple


def get_safe_xml_parser():
    """Create XXE-safe lxml XML parser.

    Disables external entity resolution, network access, and DTD validation
    to prevent XXE attacks from malicious EPUB/FB2 files.
    """
    from lxml import etree
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        huge_tree=False,
        recover=True,
    )


def get_safe_bs4_features():
    """Return bs4 features dict for XXE-safe XML parsing."""
    return {'resolve_entities': False, 'no_network': True}


def atomic_write(target_path: str, content: str, encoding: str = 'utf-8') -> None:
    """Atomically write content to target_path using tmp+rename.

    Writes to a temporary file in the same directory, then uses os.replace()
    for an atomic rename. This prevents partial/corrupt files on crash.
    """
    target_dir = os.path.dirname(os.path.abspath(target_path))
    fd = tempfile.NamedTemporaryFile(
        mode='w', dir=target_dir, delete=False, suffix='.tmp', encoding=encoding
    )
    try:
        fd.write(content)
        fd.flush()
        os.fsync(fd.fileno())
        fd.close()
        os.replace(fd.name, target_path)
    except BaseException:
        fd.close()
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise


def extract_metadata(header: str) -> Dict[str, Any]:
    """
    Extracts key metadata from the FB2 header using BeautifulSoup.
    
    Args:
        header: FB2 header XML string
        
    Returns:
        Dictionary with metadata fields
    """
    soup = BeautifulSoup(header, 'xml')
    title_info = soup.find('title-info')
    if not title_info:
        return {}

    metadata = {}
    
    # Title
    title_tag = title_info.find('book-title')
    metadata['book-title'] = title_tag.get_text() if title_tag else ""

    # Authors
    authors = []
    for author_tag in title_info.find_all('author'):
        author = {}
        for tag_name in ['first-name', 'last-name', 'middle-name', 'nickname']:
            tag = author_tag.find(tag_name)
            if tag:
                author[tag_name] = tag.get_text()
        authors.append(author)
    metadata['author'] = authors

    # Series
    series_tags = title_info.find_all('sequence')
    series_list = []
    for s_tag in series_tags:
        series = {}
        if s_tag.get('name'):
            series['name'] = s_tag.get('name')
        if s_tag.get('number'):
            series['number'] = s_tag.get('number')
        series_list.append(series)
    metadata['sequence'] = series_list

    # Annotation
    annotation_tag = title_info.find('annotation')
    if annotation_tag:
        paragraphs = [p.get_text() for p in annotation_tag.find_all('p')]
        if not paragraphs:
            paragraphs = [annotation_tag.get_text()]
        metadata['annotation'] = paragraphs
    else:
        metadata['annotation'] = []

    # Genres
    genres = [g.get_text() for g in title_info.find_all('genre')]
    metadata['genre'] = genres

    # Languages
    lang_tags = title_info.find_all('lang')
    metadata['lang'] = [l.get_text() for l in lang_tags]
    
    # Date
    date_tag = title_info.find('date')
    metadata['date'] = date_tag.get_text() if date_tag else ""
    
    # Cover
    cover_tag = title_info.find('coverpage')
    if cover_tag:
        cover_image = cover_tag.find('image')
        if cover_image:
            # FB2 files in the wild predominantly declare the xlink namespace
            # with the "l" prefix (xmlns:l=...); some tools use "xlink:" or
            # omit the prefix. Check all conventions so real-world files parse.
            metadata['cover-image'] = (
                cover_image.get('l:href')
                or cover_image.get('xlink:href')
                or cover_image.get('href')
                or ''
            )
    
    return metadata


def update_header_with_metadata(header: str, metadata: Dict[str, Any]) -> str:
    """
    Updates FB2 header with translated metadata.
    
    Args:
        header: Original FB2 header
        metadata: Dictionary with translated metadata
        
    Returns:
        Updated header string
    """
    soup = BeautifulSoup(header, 'xml')
    title_info = soup.find('title-info')
    
    if not title_info:
        return header
    
    # Update title
    if 'book-title' in metadata:
        title_tag = title_info.find('book-title')
        if title_tag:
            title_tag.string = metadata['book-title']
    
    # Update authors
    if 'author' in metadata:
        # Remove existing authors
        for author_tag in title_info.find_all('author'):
            author_tag.decompose()
        
        # Add new authors
        for author_data in metadata['author']:
            author_tag = soup.new_tag('author')
            for field, value in author_data.items():
                if value:
                    field_tag = soup.new_tag(field)
                    field_tag.string = value
                    author_tag.append(field_tag)
            title_info.append(author_tag)
    
    # Update annotation
    if 'annotation' in metadata:
        annotation_tag = title_info.find('annotation')
        if annotation_tag:
            annotation_tag.clear()
            for para in metadata['annotation']:
                p_tag = soup.new_tag('p')
                p_tag.string = para
                annotation_tag.append(p_tag)
    
    # Return serialized result, but strip </FictionBook> if BS4 added it 
    # to close an open tag in the header fragment.
    result = str(soup)
    if '</FictionBook>' in result and '</FictionBook>' not in header:
        result = result.replace('</FictionBook>', '')
        
    return result


def get_cover_image(header: str, footer: str) -> Tuple[str, str]:
    """
    Extract cover image data from FB2.
    
    Returns:
        Tuple of (image_href, image_data)
    """
    # Parse header to find cover reference
    soup = BeautifulSoup(header, 'xml')
    cover_tag = soup.find('coverpage')
    
    if not cover_tag:
        return None, None
    
    image_tag = cover_tag.find('image')
    if not image_tag:
        return None, None
    
    # Check all namespace-prefix conventions seen in real FB2 files and
    # across this codebase's writers (l:href is the dominant convention).
    image_href = (
        image_tag.get('l:href')
        or image_tag.get('xlink:href')
        or image_tag.get('href')
        or ''
    )
    if not image_href:
        return None, None
    
    # Extract image ID from href (e.g., "#cover.png" -> "cover.png")
    image_id = image_href.lstrip('#')
    
    # Search for image in footer (binary data section)
    # Look for <binary content-type="image/png" id="cover.png">
    binary_pattern = rf'<binary[^>]*content-type="[^"]*image[^"]*"[^>]*id="{re.escape(image_id)}"[^>]*>(.*?)</binary>'
    match = re.search(binary_pattern, footer, re.DOTALL | re.IGNORECASE)
    
    if match:
        image_data = match.group(1)
        return image_href, image_data
    
    return image_href, None


def replace_cover_image(header: str, footer: str, body: str, new_content: str) -> Tuple[str, str, str]:
    """
    Replace cover image in FB2.
    
    Args:
        header: FB2 header
        footer: FB2 footer (contains binary data)
        body: FB2 body
        new_content: New base64-encoded image data
        
    Returns:
        Tuple of (new_header, new_footer, new_body)
    """
    # Find existing cover image href
    image_href, _ = get_cover_image(header, footer)
    
    if not image_href:
        # No existing cover, add new one
        image_id = "cover.png"
        image_href = f"#{image_id}"
        
        # Add coverpage to header if not exists
        soup = BeautifulSoup(header, 'xml')
        title_info = soup.find('title-info')
        if title_info:
            cover_tag = soup.new_tag('coverpage')
            image_tag = soup.new_tag('image')
            # Use the "l:" prefix consistently with the rest of the codebase
            # (epub_writer.py, txt_handler.py, fb2_repair.py) so downstream
            # readers (e.g. the EPUB writer's coverpage lookup) find it.
            image_tag['l:href'] = image_href
            cover_tag.append(image_tag)
            title_info.append(cover_tag)
        # Return serialized result, but strip </FictionBook> if BS4 added it
        result = str(soup)
        if '</FictionBook>' in result and '</FictionBook>' not in header:
            result = result.replace('</FictionBook>', '')
        header = result
    
    # Extract image ID
    image_id = image_href.lstrip('#')
    
    # Remove old binary if exists
    binary_pattern = rf'<binary[^>]*id="{re.escape(image_id)}"[^>]*>.*?</binary>'
    footer = re.sub(binary_pattern, '', footer, flags=re.DOTALL | re.IGNORECASE)
    
    # Add new binary data
    # Try to detect content type from image data or default to PNG
    content_type = "image/png"
    new_binary = f'<binary content-type="{content_type}" id="{image_id}">{new_content}</binary>'
    
    # Insert before closing </FictionBook>
    if '</FictionBook>' in footer:
        footer = footer.replace('</FictionBook>', new_binary + '</FictionBook>')
    else:
        footer += new_binary
    
    return header, footer, body


_SECTION_OPEN_RE = re.compile(r'<section\b[^>]*>', re.IGNORECASE)
_SECTION_CLOSE_RE = re.compile(r'</section\s*>', re.IGNORECASE)


def _find_matching_section_end(body_str: str, content_start: int):
    """Find the closing </section> matching the section whose content starts
    at content_start, tracking nesting depth.

    Returns:
        Tuple (close_start, close_end) — span of the matching closing tag,
        or (-1, -1) if not found.
    """
    depth = 1
    pos = content_start
    while True:
        next_open = _SECTION_OPEN_RE.search(body_str, pos)
        next_close = _SECTION_CLOSE_RE.search(body_str, pos)
        if next_close is None:
            return -1, -1
        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            if depth == 0:
                return next_close.start(), next_close.end()
            pos = next_close.end()


def prepare_chunks(body: str, max_len_chunk: int) -> List[str]:
    """
    Splits the body content into sections and chunks based on max_len_chunk.
    Ensures each chunk has balanced XML tags.
    
    Args:
        body: FB2 body content
        max_len_chunk: Maximum chunk size in characters
        
    Returns:
        List of chunk strings
    """
    body_str = body
    sections = []
    
    start = 0
    while start < len(body_str):
        # Find the start of the next section (any attributes, any case)
        m = _SECTION_OPEN_RE.search(body_str, start)
        if not m:
            break

        section_start = m.end()
        section_end, section_close_end = _find_matching_section_end(body_str, section_start)

        if section_end == -1:
            break

        section = body_str[section_start:section_end]
        chunks = []

        # Split the section into chunks with tag-aware boundaries
        chunk_start = 0
        while chunk_start < len(section):
            chunk_end = chunk_start + max_len_chunk
            
            if chunk_end >= len(section):
                chunk_text = section[chunk_start:]
                chunk_text = _ensure_balanced_tags(chunk_text)
                chunks.append(chunk_text)
                break
            else:
                chunk_end = _find_chunk_boundary(section, chunk_start, chunk_end)
                chunk_text = section[chunk_start:chunk_end]
                chunk_text = _ensure_balanced_tags(chunk_text)
                chunks.append(chunk_text)
                chunk_start = chunk_end

        sections.extend(chunks)
        start = section_close_end

    if not sections:
        # Fallback: split entire body
        sections = [body_str[i:i+max_len_chunk] for i in range(0, len(body_str), max_len_chunk)]

    return sections


def _ensure_balanced_tags(chunk: str) -> str:
    """Ensure chunk has balanced XML tags (stack-based).

    Handles:
    - unclosed tags at chunk end (appends closers),
    - orphan closing tags at chunk start (prepends openers),
    - cross-nesting mismatches (explicitly closes intermediate tags).
    """
    VOID_ELEMENTS = {'br', 'hr', 'img', 'image', 'empty-line', 'input', 'meta', 'link'}
    open_stack: list[str] = []
    orphan_closers: list[str] = []
    pieces: list[str] = []
    last_end = 0
    for m in re.finditer(r'<(/?)(\w[\w-]*)([^>]*?)(/?)>', chunk):
        closing, tag, attrs, selfclose = m.groups()
        tag_lower = tag.lower()
        if selfclose or tag_lower in VOID_ELEMENTS:
            continue
        if closing:
            if open_stack and open_stack[-1] == tag_lower:
                open_stack.pop()
            elif tag_lower in open_stack:
                # Cross-nesting: explicitly close intermediate tags before this closer
                intermediate: list[str] = []
                while open_stack and open_stack[-1] != tag_lower:
                    intermediate.append(open_stack.pop())
                if open_stack:
                    open_stack.pop()
                if intermediate:
                    pieces.append(chunk[last_end:m.start()])
                    pieces.append(''.join(f'</{t}>' for t in intermediate))
                    last_end = m.start()
            else:
                # Orphan closer: no matching opener in this chunk
                orphan_closers.append(tag_lower)
        else:
            open_stack.append(tag_lower)
    rebuilt = (''.join(pieces) + chunk[last_end:]) if pieces else chunk
    prefix = ''.join(f'<{t}>' for t in reversed(orphan_closers))
    suffix = ''.join(f'</{t}>' for t in reversed(open_stack))
    return prefix + rebuilt + suffix


def _find_chunk_boundary(text: str, start: int, end: int) -> int:
    """Find a good chunk boundary (at tag boundary)."""
    # Try to find closing tag before end
    last_close = text.rfind('</', start, end)
    if last_close != -1:
        # Find the end of this closing tag
        tag_end = text.find('>', last_close)
        if tag_end != -1 and tag_end < end:
            return tag_end + 1
    
    # Try to find opening tag
    last_open = text.rfind('<', start, end)
    if last_open != -1 and last_open > start + 100:  # Minimum chunk size
        return last_open

    # Guard: never split inside a tag (between '<' and its '>')
    lt = text.rfind('<', start, end)
    if lt != -1 and lt > start:
        gt = text.find('>', lt, end)
        if gt == -1:
            # Tag opened but not closed within window — cut before it
            return lt
        if text.startswith('</', lt):
            # Closing tag — cut after it
            return gt + 1
        # Opening tag without closing pair — cut before it
        if text.find('</', lt, end) == -1:
            return lt

    return end


def prepare_chunks_with_sections(body: str, max_len_chunk: int) -> List[List[str]]:
    """
    Splits the body content into sections and chunks based on max_len_chunk.
    Preserves original FB2 section structure.
    
    Args:
        body: FB2 body content
        max_len_chunk: Maximum chunk size in characters
        
    Returns:
        List of sections, where each section is a list of chunks:
        [[section1_chunk1, section1_chunk2], [section2_chunk1], ...]
    """
    body_str = body
    sections = []
    
    start = 0
    while start < len(body_str):
        # Find the start of the next section (any attributes, any case)
        m = _SECTION_OPEN_RE.search(body_str, start)
        if not m:
            break

        section_start = m.end()
        section_end, section_close_end = _find_matching_section_end(body_str, section_start)

        if section_end == -1:
            break

        section_content = body_str[section_start:section_end]
        chunks = []

        # Split the section into chunks with tag-aware boundaries
        # Note: We don't balance tags here - chunks may have unbalanced tags
        # (e.g., <title> opened in one chunk, closed in another)
        # Full XML validation happens only on final assembled document
        chunk_start = 0
        while chunk_start < len(section_content):
            chunk_end = chunk_start + max_len_chunk
            
            if chunk_end >= len(section_content):
                chunk_text = section_content[chunk_start:]
                chunks.append(chunk_text)
                break
            else:
                chunk_end = _find_chunk_boundary(section_content, chunk_start, chunk_end)
                chunk_text = section_content[chunk_start:chunk_end]
                chunks.append(chunk_text)
                chunk_start = chunk_end

        sections.append(chunks)
        start = section_close_end

    if not sections:
        # Fallback: split entire body as one section
        chunks = []
        chunk_start = 0
        while chunk_start < len(body_str):
            chunk_end = chunk_start + max_len_chunk
            if chunk_end >= len(body_str):
                chunks.append(body_str[chunk_start:])
                break
            else:
                chunk_end = _find_chunk_boundary(body_str, chunk_start, chunk_end)
                chunks.append(body_str[chunk_start:chunk_end])
                chunk_start = chunk_end
        sections = [chunks]

    return sections
