"""
EPUB Writer

Creates EPUB files from translated FB2-like structure.
Converts internal FB2 representation back to EPUB format.
"""

import base64
import re
from datetime import datetime
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

from src.config import Config
from .epub_repair import validate_and_repair_epub

config = Config()


def create_epub_from_fb2(header: str, body: str, footer: str, output_path: str) -> str:
    """
    Create an EPUB file from FB2-like structure.
    
    Args:
        header: FB2 header XML string
        body: FB2 body XML string
        footer: FB2 footer with binary blocks
        output_path: Output file path (without extension)
    
    Returns:
        Path to created EPUB file
    """
    book = epub.EpubBook()
    
    # Parse header for metadata
    soup = BeautifulSoup(header, 'xml')
    title_info = soup.find('title-info')
    
    # --- Extract Metadata ---
    # Title
    title_tag = title_info.find('book-title') if title_info else None
    title = title_tag.get_text() if title_tag else "Unknown Title"
    book.set_title(title)
    
    # Author
    author_tag = title_info.find('author') if title_info else None
    if author_tag:
        first_name = author_tag.find('first-name')
        last_name = author_tag.find('last-name')
        nickname = author_tag.find('nickname')
        
        if first_name and last_name:
            author_name = f"{first_name.get_text()} {last_name.get_text()}"
        elif nickname:
            author_name = nickname.get_text()
        else:
            author_name = last_name.get_text() if last_name else "Unknown Author"
        
        book.add_author(author_name)
    
    # Language
    lang_tag = title_info.find('lang') if title_info else None
    lang = lang_tag.get_text() if lang_tag else "en"
    book.set_language(lang)
    
    # Identifier
    book.set_identifier(f"sunny-narrator-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    
    # Description/Annotation
    annotation_tag = title_info.find('annotation') if title_info else None
    if annotation_tag:
        # Get all paragraphs
        paragraphs = annotation_tag.find_all('p')
        if paragraphs:
            description = ' '.join(p.get_text() for p in paragraphs)
        else:
            description = annotation_tag.get_text()
        book.add_metadata('DC', 'description', description)
    
    # Genre/Subject
    genre_tags = title_info.find_all('genre') if title_info else []
    for genre_tag in genre_tags:
        book.add_metadata('DC', 'subject', genre_tag.get_text())
    
    # Series
    sequence_tag = title_info.find('sequence') if title_info else None
    if sequence_tag:
        series_name = sequence_tag.get('name', '')
        series_number = sequence_tag.get('number', '')
        if series_name:
            book.add_metadata('OPF', 'calibre:series', series_name)
            if series_number:
                book.add_metadata('OPF', 'calibre:series_index', series_number)
    
    # Publisher
    publish_info = soup.find('publish-info')
    if publish_info:
        publisher_tag = publish_info.find('publisher')
        if publisher_tag:
            book.add_metadata('DC', 'publisher', publisher_tag.get_text())
    
    # --- Extract Images from Footer ---
    images = {}
    binary_pattern = r'<binary[^>]*id="([^"]+)"[^>]*content-type="([^"]+)"[^>]*>([^<]+)</binary>'
    
    for match in re.finditer(binary_pattern, footer):
        image_id = match.group(1)
        content_type = match.group(2)
        b64_data = match.group(3)
        
        try:
            image_data = base64.b64decode(b64_data)
            images[image_id] = {
                'data': image_data,
                'content_type': content_type
            }
        except Exception as e:
            if config.debug:
                print(f"Warning: Failed to decode image {image_id}: {e}")
    
    # Add images to book
    for image_id, img_info in images.items():
        # Clean up image_id for EPUB (remove special chars)
        safe_id = re.sub(r'[^\w\-_.]', '_', image_id)
        file_name = f"images/{safe_id}"
        
        img_item = epub.EpubItem(
            uid=image_id,
            file_name=file_name,
            media_type=img_info['content_type'],
            content=img_info['data']
        )
        book.add_item(img_item)
        
        # Store mapping for body references
        images[image_id]['file_name'] = file_name
    
    # Find cover image
    coverpage_tag = title_info.find('coverpage') if title_info else None
    cover_image_id = None
    if coverpage_tag:
        image_tag = coverpage_tag.find('image')
        if image_tag:
            href = image_tag.get('l:href', '') or image_tag.get('href', '')
            if href.startswith('#'):
                cover_image_id = href[1:]
    
    # Set cover if found
    if cover_image_id and cover_image_id in images:
        cover_data = images[cover_image_id]['data']
        cover_file = images[cover_image_id]['file_name']
        book.set_cover(cover_file, cover_data)
    
    # --- Process Body into Chapters ---
    chapters = []
    chapter_count = 0
    
    # Parse body
    body_soup = BeautifulSoup(f"<body>{body}</body>", 'xml')
    
    for section in body_soup.find_all('section'):
        chapter_count += 1
        
        # Get section title
        title_tag = section.find('title')
        chapter_title = title_tag.get_text() if title_tag else f"Chapter {chapter_count}"
        
        # Clean up title for filename
        safe_title = re.sub(r'[^\w\s]', '', chapter_title)[:50]
        safe_title = re.sub(r'\s+', '_', safe_title.strip())
        file_name = f"chapter_{chapter_count}_{safe_title}.xhtml"
        
        # Process section content
        section_content = str(section)
        
        # Update image references
        for img in section.find_all('image'):
            href = img.get('l:href', '') or img.get('href', '')
            if href.startswith('#'):
                img_id = href[1:]
                if img_id in images:
                    # Replace with img tag for HTML
                    new_img = body_soup.new_tag('img')
                    new_img['src'] = images[img_id]['file_name']
                    img.replace_with(new_img)
        
        # Convert FB2 tags to HTML
        section_html = _fb2_to_html(str(section))
        
        # Create chapter
        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=file_name,
            lang=lang
        )
        chapter.content = f"<html><body>{section_html}</body></html>"
        
        book.add_item(chapter)
        chapters.append(chapter)
    
    # If no sections found, create a single chapter
    if not chapters:
        chapter = epub.EpubHtml(
            title=title,
            file_name="chapter_1.xhtml",
            lang=lang
        )
        chapter.content = f"<html><body>{_fb2_to_html(body)}</body></html>"
        book.add_item(chapter)
        chapters.append(chapter)
    
    # --- Table of Contents and Spine ---
    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Spine: nav + all chapters
    book.spine = ['nav'] + chapters
    
    # --- Write EPUB ---
    epub_path = f"{output_path}.epub"
    epub.write_epub(epub_path, book, {})
    
    if config.debug:
        print(f"EPUB created: {epub_path}")
        print(f"  Chapters: {len(chapters)}")
        print(f"  Images: {len(images)}")
    
    # --- Validate and Auto-Repair EPUB ---
    try:
        repaired_path, repairs, errors = validate_and_repair_epub(epub_path)
        
        if repairs and repairs[0] != "EPUB is valid":
            import logging
            logger = logging.getLogger(__name__)
            logger.info("EPUB Auto-Repair: " + " | ".join(repairs))
        
        if errors:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"EPUB validation errors remaining: {len(errors)}")
            for error in errors[:5]:
                logger.warning(f"  {error}")
    except Exception as e:
        # Don't fail if validation/repair fails
        if config.debug:
            print(f"EPUB validation warning: {e}")
    
    return epub_path


def _fb2_to_html(fb2_content: str) -> str:
    """
    Convert FB2 XML tags to HTML tags.
    
    FB2 → HTML mapping:
    <p> → <p>
    <strong> → <strong>
    <emphasis> → <em>
    <subtitle> → <h2>
    <cite> → <blockquote>
    <poem> → <div class="poem">
    <stanza> → <div class="stanza">
    <v> → <p class="verse">
    <empty-line/> → <br/>
    """
    html = fb2_content
    
    # Simple tag replacements
    replacements = [
        (r'<emphasis>', '<em>'),
        (r'</emphasis>', '</em>'),
        (r'<subtitle>', '<h2>'),
        (r'</subtitle>', '</h2>'),
        (r'<cite>', '<blockquote>'),
        (r'</cite>', '</blockquote>'),
        (r'<poem>', '<div class="poem">'),
        (r'</poem>', '</div>'),
        (r'<stanza>', '<div class="stanza">'),
        (r'</stanza>', '</div>'),
        (r'<v>', '<p class="verse">'),
        (r'</v>', '</p>'),
        (r'<empty-line\s*/?>', '<br/>'),
        (r'<title>', '<h1>'),
        (r'</title>', '</h1>'),
        # Remove section tags (we handle them separately)
        (r'</?section[^>]*>', ''),
    ]
    
    for pattern, replacement in replacements:
        html = re.sub(pattern, replacement, html, flags=re.IGNORECASE)
    
    # Handle image tags
    # <image l:href="#id"/> → <img src="images/id"/>
    def replace_image(match):
        href = match.group(1)
        if href.startswith('#'):
            img_id = href[1:]
            return f'<img src="images/{img_id}"/>'
        return match.group(0)
    
    html = re.sub(r'<image[^>]*l:href=["\']([^"\']+)["\'][^>]*/>', replace_image, html)
    
    return html


def fb2_to_epub(fb2_path: str, output_path: str = None) -> str:
    """
    Convert an FB2 file to EPUB.
    
    Args:
        fb2_path: Path to FB2 file
        output_path: Output path (without extension). If None, same as input.
    
    Returns:
        Path to created EPUB file
    """
    if output_path is None:
        output_path = fb2_path.rsplit('.', 1)[0]
    
    # Parse FB2
    with open(fb2_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into header, body, footer
    start_body = content.find('<body')
    end_body_tag = content.find('</body>')
    
    if start_body == -1 or end_body_tag == -1:
        raise ValueError("Invalid FB2 structure")
    
    end_start_body = content.find('>', start_body) + 1
    end_body = end_body_tag
    
    header = content[:start_body]
    body = content[end_start_body:end_body]
    footer = content[end_body_tag + len('</body>'):]
    
    return create_epub_from_fb2(header, body, footer, output_path)