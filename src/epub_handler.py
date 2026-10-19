"""
EPUB file handler.

Handles parsing and conversion of EPUB files to FB2 format.
Uses fb2_handler for common XML operations.
"""

from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr
from datetime import datetime
import logging

from bs4 import BeautifulSoup, Comment, NavigableString
import ebooklib
from ebooklib import epub

from src.config import Config

config = Config()
logger = logging.getLogger(__name__)

__all__ = [
    'parse_epub',
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
    from src.html_text import html_to_paragraphs
    metadata['annotation'] = html_to_paragraphs(description[0][0]) if description else []
    
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
            authors_xml += f"<first-name>{_xml_escape(str(author['first-name']))}</first-name>"
        if author.get('last-name'):
            authors_xml += f"<last-name>{_xml_escape(str(author['last-name']))}</last-name>"
        authors_xml += "</author>"
    
    # Build annotation
    annotation_xml = ""
    if metadata.get('annotation'):
        annotation_xml = "<annotation>"
        for para in metadata['annotation']:
            annotation_xml += f"<p>{_xml_escape(str(para))}</p>"
        annotation_xml += "</annotation>"
    
    # Build genres
    genres_xml = ""
    for genre in metadata.get('genre', []):
        genres_xml += f"<genre>{_xml_escape(str(genre))}</genre>"
    
    # Build languages
    lang_xml = ""
    for lang in metadata.get('lang', ['en']):
        lang_xml += f"<lang>{lang}</lang>"
    
    # Build date
    date_xml = f"<date>{_xml_escape(str(metadata.get('date', '')))}</date>" if metadata.get('date') else ""
    
    # Build sequence
    sequence_xml = ""
    for seq in metadata.get('sequence', []):
        sequence_xml += f'<sequence name={_xml_quoteattr(str(seq.get("name", "")))} number={_xml_quoteattr(str(seq.get("number", "")))} />'
    
    header = f"""<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:xlink="http://www.w3.org/1999/xlink">
<description>
<title-info>
{genres_xml}
{authors_xml}
<book-title>{_xml_escape(str(metadata.get('book-title', '')))}</book-title>
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


# DEF-M19 (F3b stage 1). Block containers we walk into (their children are
# converted, stray text between them becomes a paragraph). Everything else
# that is not p/h1-h6/ul/ol/blockquote/hr is counted per tag and reported
# once per document: nothing is lost silently any more. Tables are dropped
# WITH a warning on this stage - their text is NOT carried over; full
# support is stage 2.
_WALK_INTO_TAGS = frozenset({'html', 'body', 'div', 'article', 'section',
                             'main', 'aside', 'header', 'footer', 'form',
                             'center'})
_HEADING_TAGS = frozenset({'h1', 'h2', 'h3', 'h4', 'h5', 'h6'})


def convert_html_to_fb2_section(soup) -> str:
    """
    Convert HTML content to FB2 section.

    Handles (stage 1 of DEF-M19): p (inline formatting preserved), h1-h6
    (<subtitle>), ul/ol (<p> with a bullet/number prefix - this project's
    FictionBook.xsd does not allow <list> in a section), blockquote
    (<cite>), hr (<empty-line/>), and bare text inside containers such as
    div. Lists nested deeper than one level flatten into the parent item.

    Args:
        soup: BeautifulSoup object with HTML content

    Returns:
        FB2 section string
    """
    parts = ['<section>']
    dropped = {}

    def emit_blocks(node, out):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    out.append(f"<p>{_xml_escape(text)}</p>")
                continue
            emit_one(child, out)

    def emit_one(el, out):
        name = el.name or 'unknown'
        if name in _HEADING_TAGS:
            out.append(f"<subtitle>{_xml_escape(el.get_text())}</subtitle>")
        elif name == 'p':
            out.append(f"<p>{convert_inline_html(el)}</p>")
        elif name in ('ul', 'ol'):
            for i, li in enumerate(el.find_all('li', recursive=False), 1):
                prefix = f"{i}. " if name == 'ol' else '\u2022 '
                text = convert_inline_html(li).strip()
                if text:
                    out.append(f"<p>{prefix}{text}</p>")
        elif name == 'blockquote':
            inner = []
            emit_blocks(el, inner)
            if inner:
                out.append('<cite>' + ''.join(inner) + '</cite>')
        elif name == 'hr':
            out.append('<empty-line/>')
        elif name in _WALK_INTO_TAGS:
            emit_blocks(el, out)
        else:
            dropped[name] = dropped.get(name, 0) + 1

    emit_blocks(soup, parts)

    if dropped:
        total = sum(dropped.values())
        detail = ', '.join(f'<{t}> x{c}' for t, c in sorted(dropped.items()))
        logger.warning(
            f"Dropped {total} unsupported block(s) converting HTML to FB2: "
            f"{detail}; their text content is lost (stage-1 conversion, "
            f"tables included)")

    parts.append('</section>')
    return "\n".join(parts)


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
            tag_content = _xml_escape(child.get_text())

            # Map HTML tags to FB2 tags
            if tag_name in ['b', 'strong']:
                content += f"<strong>{tag_content}</strong>"
            elif tag_name in ['i', 'em']:
                content += f"<emphasis>{tag_content}</emphasis>"
            elif tag_name == 'a':
                href = child.get('href', '')
                content += f'<a href={_xml_quoteattr(href)}>{tag_content}</a>'
            else:
                content += tag_content
        else:
            # Text node
            content += _xml_escape(str(child))

    return content
