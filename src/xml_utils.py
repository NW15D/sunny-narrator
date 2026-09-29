"""
XML/FB2 utility functions.

Common utilities for XML parsing, metadata extraction, and FB2 manipulation.
Used by fb2_handler, epub_handler, txt_handler.
"""

import base64
import binascii
import re
import os
import tempfile
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, Tuple

IMAGE_EXTENSIONS = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
                    'image/webp': '.webp', 'image/svg+xml': '.svg'}


def sniff_image_type(data: bytes, declared: str = '') -> Optional[str]:
    """Media type from the image bytes; the declared type is only a fallback
    (FB2 files and image APIs both mislabel images)."""
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if b'<svg' in data[:1024]:
        return 'image/svg+xml'
    declared = (declared or '').strip().lower()
    if declared == 'image/jpg':
        return 'image/jpeg'
    return declared if declared in IMAGE_EXTENSIONS else None


def sniff_base64_image_type(b64: str, default: str = 'image/png') -> str:
    try:
        head = base64.b64decode(re.sub(r'\s+', '', b64)[:64])
    except (binascii.Error, ValueError):
        return default
    return sniff_image_type(head) or default


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


_AUTHOR_FIELD_ORDER = ['first-name', 'middle-name', 'last-name', 'nickname',
                       'home-page', 'email', 'id']


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
    
    # Update authors. They must stay in front of <book-title> (FB2 schema
    # order), so the new ones go where the old ones were.
    if metadata.get('author'):
        existing = title_info.find_all('author', recursive=False)
        new_authors = []
        for author_data in metadata['author']:
            author_tag = soup.new_tag('author')
            for field in _AUTHOR_FIELD_ORDER:
                if author_data.get(field):
                    field_tag = soup.new_tag(field)
                    field_tag.string = author_data[field]
                    author_tag.append(field_tag)
            new_authors.append(author_tag)
        anchor = existing[0] if existing else title_info.find('book-title', recursive=False)
        for author_tag in new_authors:
            if anchor is not None:
                anchor.insert_before(author_tag)
            else:
                title_info.append(author_tag)
        for author_tag in existing:
            author_tag.decompose()

    # Update language: the book is now in the target language; keep the
    # original one as <src-lang>.
    if metadata.get('lang'):
        lang = metadata['lang']
        lang = str(lang[0] if isinstance(lang, list) and lang else lang).strip()
        lang_tag = title_info.find('lang', recursive=False)
        if lang and lang_tag is not None:
            old_lang = lang_tag.get_text().strip()
            if old_lang and old_lang != lang and title_info.find('src-lang', recursive=False) is None:
                src_tag = soup.new_tag('src-lang')
                src_tag.string = old_lang
                lang_tag.insert_after(src_tag)
            lang_tag.string = lang
        elif lang:
            lang_tag = soup.new_tag('lang')
            lang_tag.string = lang
            anchor = next((title_info.find(n, recursive=False)
                           for n in ('src-lang', 'translator', 'sequence')
                           if title_info.find(n, recursive=False) is not None), None)
            if anchor is not None:
                anchor.insert_before(lang_tag)
            else:
                title_info.append(lang_tag)

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
    # Attribute order varies between FB2 producers (id first is common)
    binary_pattern = (rf'<binary(?=[^>]*\bcontent-type=["\'][^"\']*image)'
                      rf'(?=[^>]*\bid=["\']{re.escape(image_id)}["\'])[^>]*>(.*?)</binary>')
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
            # <coverpage> precedes <lang> in the FB2 schema order
            lang_tag = title_info.find('lang', recursive=False)
            if lang_tag is not None:
                lang_tag.insert_before(cover_tag)
            else:
                title_info.append(cover_tag)
        # Return serialized result, but strip </FictionBook> if BS4 added it
        result = str(soup)
        if '</FictionBook>' in result and '</FictionBook>' not in header:
            result = result.replace('</FictionBook>', '')
        header = result
    
    # Extract image ID
    image_id = image_href.lstrip('#')
    
    # Remove old binary if exists
    binary_pattern = rf'<binary(?=[^>]*\bid=["\']{re.escape(image_id)}["\'])[^>]*>.*?</binary>'
    footer = re.sub(binary_pattern, '', footer, flags=re.DOTALL | re.IGNORECASE)
    
    # Add new binary data (image models return PNG or JPEG depending on the provider)
    content_type = sniff_base64_image_type(new_content)
    new_binary = f'<binary content-type="{content_type}" id="{image_id}">{new_content}</binary>'
    
    # Insert before closing </FictionBook>
    if '</FictionBook>' in footer:
        footer = footer.replace('</FictionBook>', new_binary + '</FictionBook>')
    else:
        footer += new_binary
    
    return header, footer, body
