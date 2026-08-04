"""
EPUB file handler.

Handles parsing and conversion of EPUB files to FB2 format.
Uses fb2_handler for common XML operations.
"""

import re
import base64
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

from src.config import Config
from src.fb2_handler import (
    extract_metadata,
    update_header_with_metadata,
    get_cover_image,
    replace_cover_image,
    prepare_chunks
)

config = Config()

__all__ = [
    'parse_epub',
    'convert_epub_to_fb2_structure',
    'extract_epub_metadata',
    'extract_epub_body'
]


def parse_epub(file_path: str) -> tuple:
    """
    Parses an EPUB file and converts to FB2-like structure.
    
    Args:
        file_path: Path to EPUB file
        
    Returns:
        Tuple of (body, header, footer)
    """
    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read EPUB file: {e}")
    
    # Extract metadata
    metadata = extract_epub_metadata(book)
    
    # Build FB2 header
    header = build_fb2_header_from_metadata(metadata)
    
    # Extract body content
    body = extract_epub_body(book)
    
    # Footer (empty for EPUB conversion, will be populated if images added)
    footer = ""
    
    return body, header, footer


def extract_epub_metadata(book) -> dict:
    """
    Extract metadata from EPUB book.
    
    Args:
        book: EPUB book object
        
    Returns:
        Dictionary with metadata
    """
    metadata = {}
    
    # Title
    title = book.get_metadata('DC', 'title')
    metadata['book-title'] = title[0][0] if title else "Unknown Title"
    
    # Author
    creator = book.get_metadata('DC', 'creator')
    author_name = creator[0][0] if creator else "Unknown Author"
    
    # Parse author name
    author_first = ""
    author_last = author_name
    if " " in author_name:
        parts = author_name.rsplit(" ", 1)
        author_first = parts[0]
        author_last = parts[1]
    
    metadata['author'] = [{
        'first-name': author_first,
        'last-name': author_last
    }]
    
    # Description/Annotation
    description = book.get_metadata('DC', 'description')
    annotation = description[0][0] if description else ""
    metadata['annotation'] = [annotation] if annotation else []
    
    # Language
    language_meta = book.get_metadata('DC', 'language')
    metadata['lang'] = [language_meta[0][0] if language_meta else "en"]
    
    # Date
    date_meta = book.get_metadata('DC', 'date')
    metadata['date'] = date_meta[0][0] if date_meta else str(datetime.now().year)
    
    # Genre (Subject)
    subject = book.get_metadata('DC', 'subject')
    metadata['genre'] = [subject[0][0] if subject else "unknown"]
    
    # Series
    series_name = ""
    series_number = ""
    
    calibre_series = book.get_metadata('OPF', 'calibre:series')
    if calibre_series:
        series_name = calibre_series[0][0]
    
    calibre_index = book.get_metadata('OPF', 'calibre:series_index')
    if calibre_index:
        series_number = calibre_index[0][0]
    
    if not series_name:
        belongs_to = book.get_metadata('OPF', 'belongs-to-collection')
        if belongs_to:
            series_name = belongs_to[0][0]
            group_position = book.get_metadata('OPF', 'group-position')
            if group_position:
                series_number = group_position[0][0]
    
    if series_name:
        metadata['sequence'] = [{'name': series_name, 'number': series_number}]
    else:
        metadata['sequence'] = []
    
    return metadata


def build_fb2_header_from_metadata(metadata: dict) -> str:
    """
    Build FB2 header from metadata dictionary.
    
    Args:
        metadata: Metadata dictionary
        
    Returns:
        FB2 header string
    """
    # Build author tags
    authors_xml = ""
    for author in metadata.get('author', []):
        authors_xml += "<author>"
        if author.get('first-name'):
            authors_xml += f"<first-name>{author['first-name']}</first-name>"
        if author.get('last-name'):
            authors_xml += f"<last-name>{author['last-name']}</last-name>"
        authors_xml += "</author>"
    
    # Build annotation
    annotation_xml = ""
    if metadata.get('annotation'):
        annotation_xml = "<annotation>"
        for para in metadata['annotation']:
            annotation_xml += f"<p>{para}</p>"
        annotation_xml += "</annotation>"
    
    # Build genres
    genres_xml = ""
    for genre in metadata.get('genre', []):
        genres_xml += f"<genre>{genre}</genre>"
    
    # Build languages
    lang_xml = ""
    for lang in metadata.get('lang', ['en']):
        lang_xml += f"<lang>{lang}</lang>"
    
    # Build date
    date_xml = f"<date>{metadata.get('date', '')}</date>" if metadata.get('date') else ""
    
    # Build sequence
    sequence_xml = ""
    for seq in metadata.get('sequence', []):
        sequence_xml += f'<sequence name="{seq.get("name", "")}" number="{seq.get("number", "")}" />'
    
    header = f"""<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:xlink="http://www.w3.org/1999/xlink">
<description>
<title-info>
{genres_xml}
<author>{authors_xml}</author>
<book-title>{metadata.get('book-title', '')}</book-title>
{annotation_xml}
{date_xml}
{lang_xml}
{sequence_xml}
</title-info>
</description>
<body>
"""
    return header


def extract_epub_body(book) -> str:
    """
    Extract body content from EPUB book.
    
    Args:
        book: EPUB book object
        
    Returns:
        FB2 body string
    """
    body_content = []
    
    # Get all documents (chapters)
    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    
    for item in items:
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Parse HTML content
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            
            # Convert to FB2 format
            fb2_section = convert_html_to_fb2_section(soup)
            if fb2_section:
                body_content.append(fb2_section)
    
    # Wrap in body tags
    body = "<body>\n"
    body += "\n".join(body_content)
    body += "\n</body>\n"
    
    return body


def convert_html_to_fb2_section(soup) -> str:
    """
    Convert HTML content to FB2 section.
    
    Args:
        soup: BeautifulSoup object with HTML content
        
    Returns:
        FB2 section string
    """
    section_parts = ['<section>']
    
    # Process paragraphs
    for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        tag_name = element.name
        
        if tag_name.startswith('h'):
            # Convert heading to subtitle
            section_parts.append(f"<subtitle>{element.get_text()}</subtitle>")
        elif tag_name == 'p':
            # Convert paragraph, preserving inline formatting
            para_content = convert_inline_html(element)
            section_parts.append(f"<p>{para_content}</p>")
    
    section_parts.append('</section>')
    return "\n".join(section_parts)


def convert_inline_html(element) -> str:
    """
    Convert inline HTML tags to FB2 inline tags.
    
    Args:
        element: BeautifulSoup element
        
    Returns:
        String with FB2 inline tags
    """
    content = ""
    
    for child in element.children:
        if hasattr(child, 'name') and child.name:
            tag_name = child.name
            tag_content = child.get_text()
            
            # Map HTML tags to FB2 tags
            if tag_name in ['b', 'strong']:
                content += f"<strong>{tag_content}</strong>"
            elif tag_name in ['i', 'em']:
                content += f"<emphasis>{tag_content}</emphasis>"
            elif tag_name == 'a':
                href = child.get('href', '')
                content += f'<a href="{href}">{tag_content}</a>'
            else:
                content += tag_content
        else:
            # Text node
            content += str(child)
    
    return content
