"""Markdown utilities for processing and generating markdown content."""
import re
from typing import List, Union
from bs4 import BeautifulSoup


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
    pattern = r'^(#{1,6})\s+(.+)$'
    
    for line in content.split('\n'):
        match = re.match(pattern, line)
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
    # Convert to lowercase, replace spaces with hyphens
    heading_id = text.lower()
    heading_id = re.sub(r'[^\w\s-]', '', heading_id)
    heading_id = re.sub(r'\s+', '-', heading_id)
    heading_id = re.sub(r'-+', '-', heading_id)
    heading_id = heading_id.strip('-')
    
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
    - Calibre classes
    
    Args:
        text: Text containing Calibre markers
        
    Returns:
        Cleaned text
    """
    # Remove HTML comments with numbers
    text = re.sub(r'<!--\s*\d+\s*-->', '', text)
    
    # Remove Calibre anchors {#...}
    text = re.sub(r'\{#[^}]+\}', '', text)
    
    # Remove Calibre classes {.calibre1}
    text = re.sub(r'\s*\{\.[^\}]+\}', '', text)
    
    return text
