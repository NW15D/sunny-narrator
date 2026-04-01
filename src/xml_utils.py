"""
XML/FB2 utility functions.

Common utilities for XML parsing, metadata extraction, and FB2 manipulation.
Used by fb2_handler, epub_handler, txt_handler.
"""

import re
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Tuple


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
            metadata['cover-image'] = cover_image.get('xlink:href', '')
    
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
    
    return str(soup)


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
    
    image_href = image_tag.get('xlink:href', '')
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
            image_tag['xlink:href'] = image_href
            cover_tag.append(image_tag)
            title_info.append(cover_tag)
        header = str(soup)
    
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
    start_tags = {'<section>', '<SECTION>'}
    
    start = 0
    while start < len(body_str):
        # Find the start of the next section
        found_start_tag = None
        for tag in start_tags:
            pos = body_str.find(tag, start)
            if pos != -1 and (found_start_tag is None or pos < found_start_tag[1]):
                found_start_tag = (tag, pos)

        if not found_start_tag:
            break

        section_start = found_start_tag[1] + len(found_start_tag[0])
        section_end = body_str.find('</section>', section_start)

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
        start = section_end + len('</section>')

    if not sections:
        # Fallback: split entire body
        sections = [body_str[i:i+max_len_chunk] for i in range(0, len(body_str), max_len_chunk)]

    return sections


def _ensure_balanced_tags(chunk: str) -> str:
    """Ensure chunk has balanced XML tags."""
    # Simple balancing - add closing tags if needed
    open_tags = len(re.findall(r'<(?!/)([^>/]+?)(?:\s[^>]*)?>', chunk))
    close_tags = len(re.findall(r'</[^>]+>', chunk))
    
    # Add missing closing tags
    while open_tags > close_tags:
        chunk += '</section>'
        close_tags += 1
    
    return chunk


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
    start_tags = {'<section>', '<SECTION>'}
    
    start = 0
    while start < len(body_str):
        # Find the start of the next section
        found_start_tag = None
        for tag in start_tags:
            pos = body_str.find(tag, start)
            if pos != -1 and (found_start_tag is None or pos < found_start_tag[1]):
                found_start_tag = (tag, pos)

        if not found_start_tag:
            break

        section_start = found_start_tag[1] + len(found_start_tag[0])
        section_end = body_str.find('</section>', section_start)

        if section_end == -1:
            break

        section_content = body_str[section_start:section_end]
        chunks = []

        # Split the section into chunks with tag-aware boundaries
        chunk_start = 0
        while chunk_start < len(section_content):
            chunk_end = chunk_start + max_len_chunk
            
            if chunk_end >= len(section_content):
                chunk_text = section_content[chunk_start:]
                chunk_text = _ensure_balanced_tags(chunk_text)
                chunks.append(chunk_text)
                break
            else:
                chunk_end = _find_chunk_boundary(section_content, chunk_start, chunk_end)
                chunk_text = section_content[chunk_start:chunk_end]
                chunk_text = _ensure_balanced_tags(chunk_text)
                chunks.append(chunk_text)
                chunk_start = chunk_end

        sections.append(chunks)
        start = section_end + len('</section>')

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
