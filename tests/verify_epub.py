import sys
import os
import base64
from ebooklib import epub

# Add project root to path
sys.path.append(os.getcwd())
try:
    from src.epub_handler import parse_epub
except ImportError:
    # Fallback if src not explicitly a package in some envs
    sys.path.append(os.path.join(os.getcwd(), 'src'))
    from epub_handler import parse_epub
from icecream import ic

def create_mock_epub(filename):
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier('id123456')
    book.set_title('Test Book Title')
    book.set_language('en')
    book.add_author('Test Author')
    book.add_metadata('DC', 'description', 'This is a test description.')
    book.add_metadata('DC', 'publisher', 'Test Publisher')
    book.add_metadata('DC', 'subject', 'Science Fiction')
    
    # Create chapter
    c1 = epub.EpubHtml(title='Intro', file_name='chap_01.xhtml', lang='en')
    c1.content = '<h1>Introduction</h1><p>Hello world.</p><img src="images/test_image.jpg" alt="test image"/>'
    book.add_item(c1)

    # Create image
    # 1x1 red pixel
    img_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    img_item = epub.EpubItem(uid='image_001', file_name='images/test_image.jpg', media_type='image/jpeg', content=img_data)
    book.add_item(img_item)
    
    # Set cover (optional, but good to test)
    # Re-use the same image for cover
    book.set_cover("images/cover.jpg", img_data)

    # Define Table of Contents
    book.toc = (epub.Link('chap_01.xhtml', 'Introduction', 'intro'), (epub.Section('Languages'), (c1, )) )

    # Add default NCX and Nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define CSS style
    style = 'BODY {color: white;}'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(nav_css)

    # Basic spine
    book.spine = ['nav', c1]

    epub.write_epub(filename, book, {})
    return filename

def test_parse_epub():
    filename = 'test_mock.epub'
    try:
        create_mock_epub(filename)
        print(f"Created {filename}")
        
        body, header, footer = parse_epub(filename)
        
        print("\n--- Header ---")
        print(header[:500] + "...") # Print start
        
        print("\n--- Body Snippet ---")
        print(body[:200] + "...")

        print("\n--- Footer Snippet ---")
        print(footer[:200] + "...")

        # Assertions
        assert "<book-title>Test Book Title</book-title>" in header
        assert "<first-name>Test</first-name>" in header
        assert "<last-name>Author</last-name>" in header
        assert "<annotation><p>This is a test description.</p></annotation>" in header
        assert 'l:href="#images/test_image.jpg"' in body, "Body image link broken"
        assert '<binary id="images/test_image.jpg"' in footer
        assert "image/jpeg" in footer
        
        print("\nSUCCESS: All assertions passed!")

    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    test_parse_epub()
