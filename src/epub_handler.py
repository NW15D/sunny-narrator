import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

import src.fb2_handler as fb2
from src.config import Config

config = Config()
import base64
import mimetypes
from datetime import datetime

def parse_epub(file_path):
    """
    Parses an EPUB file and converts its content into an FB2-like XML structure 
    (body, header, footer) for compatibility with the existing translation pipeline.
    """
    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read EPUB file: {e}")

    # --- Extract Metadata ---
    # Title
    title = book.get_metadata('DC', 'title')
    title = title[0][0] if title else "Unknown Title"
    
    # Author
    creator = book.get_metadata('DC', 'creator')
    author = creator[0][0] if creator else "Unknown Author"
    author_first = ""
    author_last = author
    if " " in author:
        parts = author.rsplit(" ", 1)
        author_first = parts[0]
        author_last = parts[1]

    # Description/Annotation
    description = book.get_metadata('DC', 'description')
    annotation = description[0][0] if description else ""
    
    # Language
    language_meta = book.get_metadata('DC', 'language')
    lang = language_meta[0][0] if language_meta else "en"

    # Date
    date_meta = book.get_metadata('DC', 'date')
    date_str = date_meta[0][0] if date_meta else str(datetime.now().year)

    # Genre (Subject)
    subject = book.get_metadata('DC', 'subject')
    genre = subject[0][0] if subject else "unknown"

    # Publisher
    publisher_meta = book.get_metadata('DC', 'publisher')
    publisher = publisher_meta[0][0] if publisher_meta else ""

    # Cover Image
    cover_image_id = None
    # Try to find cover image id
    # 1. Check metadata
    if book.get_metadata('OPF', 'cover'):
         cover_image_id = book.get_metadata('OPF', 'cover')[0][0]
    
    # --- Process Images ---
    images = {} # Map filename to base64 content
    image_content_types = {}
    
    # Iterate over all items to find images
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            # item.get_name() usually contains the path inside the epub, e.g. 'images/cover.jpg'
            # We use the filename as ID for FB2 binary blocks
            image_id = item.get_name() 
            content = item.get_content()
            b64_content = base64.b64encode(content).decode('utf-8')
            media_type = item.media_type
            
            images[image_id] = b64_content
            image_content_types[image_id] = media_type

    # Construct the binary blocks for the footer
    binary_blocks = ""
    for img_id, b64_data in images.items():
        media_type = image_content_types.get(img_id, 'image/jpeg')
        # FB2 binary id should simple, often people use the filename. 
        # We need to make sure we reference it correctly in the body.
        # Clean up the ID for FB2: remove folders if possible or keep as is? 
        # Usually FB2 ids are just filenames. Let's keep the full item name but ensure it's valid.
        # Actually FB2 hrefs are #id. 
        
        binary_blocks += f'<binary id="{img_id}" content-type="{media_type}">{b64_data}</binary>\n'

    # --- Construct Header ---
    
    # Format annotation if present
    annotation_xml = ""
    if annotation:
        annotation_xml = f"<annotation><p>{annotation}</p></annotation>"
    
    publisher_xml = ""
    if publisher:
        publisher_xml = f"<publisher>{publisher}</publisher>"

    coverpage_xml = ""
    # If we found a cover image, add it to title-info
    # We need to find the filename associated with the cover_id if it was an ID
    cover_href = ""
    if cover_image_id:
        # If the metadata gave us an ID, find the item name
        item = book.get_item_with_id(cover_image_id)
        if item:
            cover_href = item.get_name()
    
    # Fallback: if no cover found in metadata, check if 'cover.jpg' or similar exists in images
    if not cover_href:
        for img_name in images.keys():
            if 'cover' in img_name.lower():
                cover_href = img_name
                break
    
    if cover_href:
        coverpage_xml = f"<coverpage><image l:href=\"#{cover_href}\"/></coverpage>"

    header = f"""<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description>
    <title-info>
        <genre>{genre}</genre>
        <author>
            <first-name>{author_first}</first-name>
            <last-name>{author_last}</last-name>
        </author>
        <book-title>{title}</book-title>
        {annotation_xml}
        <date>{date_str}</date>
        {coverpage_xml}
        <lang>{lang}</lang>
        <translator><nickname>Sunny narrator opensource AI translator </nickname> <email>n@uwns.org</email> </translator>
    </title-info>
    <publish-info>
        {publisher_xml}
    </publish-info>
</description>
"""

    footer = f"{binary_blocks}</FictionBook>"

    # --- Process Body ---
    body_content = ""
    
    # Iterate through items of type DOCUMENT (HTML files)
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        
        if soup.body:
            # Cleanup
            for script in soup(["script", "style", "title", "meta", "link"]):
                script.decompose()
            
            # Handle Images in Body
            # Update img src to point to our internal binary blocks
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    # In EPUB, src is relative to the document. 
                    # We need to resolve it to the full path key in our 'images' dict.
                    # This can be tricky.
                    # Attempt 1: Just check if the basename matches any key (simplistic)
                    # Attempt 2: Resolve path relative to item.get_name()
                    
                    # For now, let's try to match loosely or assume flatten structure if simple
                    # But correct way:
                    # item.get_name() checks 'Text/chapter1.html'. src might be '../Images/img1.jpg'.
                    # We probably don't need full path resolution if we're lucky, but let's try.
                    
                    # Current strategy: if src is in images keys, use it.
                    # The keys in `images` are `item.get_name()` (e.g. 'OEBPS/images/cat.jpg')
                    
                    # We need to resolve the relative path.
                    # Since we don't have a full path resolver easily without os.path, 
                    # let's try to find the image by suffix matching if exact fail.
                    
                    found_key = None
                    if src in images:
                        found_key = src
                    else:
                        # Try to resolve relative path?
                        # Since `ebooklib` doesn't strictly enforce file system paths, 
                        # let's try simple name matching if unique.
                        src_name = src.split('/')[-1]
                        for img_key in images:
                             if img_key.endswith(src_name):
                                 found_key = img_key
                                 break
                    
                    if found_key:
                        img['l:href'] = f"#{found_key}" # FB2 uses xlink:href usually l:href
                        del img['src'] # Remove src
                    else:
                        # Image not found in package, remove or keep?
                        pass

            # Update 'a' tags href? standard parsing.

            chapter_content = soup.body.decode_contents()
            body_content += f"<section>\n{chapter_content}\n</section>\n"

    # Combine into a single body block
    body = f"<body>\n{body_content}\n</body>"
    
    if config.debug:
        print(len(body))
    return body, header, footer
def prepare_chunks(body, max_len_chunk):
    """
    Uses the existing FB2 chunking logic since we formatted the EPUB body 
    to look like FB2 (sections).
    """
    return fb2.prepare_chunks(body, max_len_chunk)

def get_cover_image(header, footer):
    """
    Wrapper for fb2_handler.get_cover_image since the structure is identical.
    """
    return fb2.get_cover_image(header, footer)

def replace_cover_image(header, footer, body, new_content):
    """
    Wrapper for fb2_handler.replace_cover_image.
    """
    return fb2.replace_cover_image(header, footer, body, new_content)
