import os
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

try:
    from charset_normalizer import from_bytes as detect_encoding
except ImportError:
    detect_encoding = None

import src.fb2_handler as fb2


def _read_with_fallback(file_path):
    """Read a text file trying multiple encodings.

    Fallback chain: utf-8 → charset-normalizer → cp1251 → latin-1 (errors='replace').
    """
    with open(file_path, 'rb') as f:
        raw = f.read()

    # 1. Try UTF-8
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # 2. Try charset-normalizer if available
    if detect_encoding is not None:
        result = detect_encoding(raw).best()
        if result is not None:
            return str(result)

    # 3. Try cp1251 (common for Russian text)
    try:
        return raw.decode('cp1251')
    except UnicodeDecodeError:
        pass

    # 4. Last resort: latin-1 never raises (maps all 256 byte values)
    return raw.decode('latin-1', errors='replace')


def parse_txt(file_path):
    """
    Parses a TXT file and converts it into an FB2-like XML structure.
    Returns body, header, footer.
    """
    try:
        content = _read_with_fallback(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read TXT file: {e}")

    # Create a simple header
    file_name = os.path.basename(file_path)
    title = os.path.splitext(file_name)[0]
    date_str = str(datetime.now().year)
    
    header = f"""<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description>
    <title-info>
        <genre>unknown</genre>
        <author><first-name></first-name><last-name>Unknown</last-name></author>
        <book-title>{xml_escape(title)}</book-title>
        <date>{date_str}</date>
        <lang>en</lang>
    </title-info>
</description>
"""

    # Create body
    # Wrap text in paragraphs
    paragraphs = content.split('\n\n')
    body_content = ""
    for p in paragraphs:
        p = p.strip()
        if p:
            # Escape XML chars
            p = p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            body_content += f"<p>{p}</p>\n"
            
    # Wrap in a single section so the chunker can find it
    body = f"<body>\n<section>\n{body_content}\n</section>\n</body>"
    
    footer = "</FictionBook>"
    
    return body, header, footer

def prepare_chunks(body, max_len_chunk):
    """
    Uses the existing FB2 chunking logic.
    
    Need TXT chunking logic with MAX_LEN_CHUNK

    """
    return fb2.prepare_chunks(body, max_len_chunk)

def get_cover_image(header, footer):
    """
    TXT usually doesn't have an embedded cover.
    Returns None.
    """
    return None

def replace_cover_image(header, footer, body, new_content):
    """
    Replacing cover image in TXT (converted to FB2-structure).
    If we want to support it, we could insert the text description into the body.
    """
    # Reuse fb2 logic if we want to allow inserting text description
    return fb2.replace_cover_image(header, footer, body, new_content)
