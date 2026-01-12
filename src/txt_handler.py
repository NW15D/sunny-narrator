import os
from datetime import datetime
import src.fb2_handler as fb2

def parse_txt(file_path):
    """
    Parses a TXT file and converts it into an FB2-like XML structure.
    Returns body, header, footer.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise ValueError(f"Failed to read TXT file: {e}")

    # Create a simple header
    file_name = os.path.basename(file_path)
    title = os.path.splitext(file_name)[0]
    date_str = str(datetime.now().year)
    
    header = ""


    # Create body
    # Wrap text in paragraphs
    # Split by double newlines for paragraphs?
    paragraphs = content.split('\n\n')
    body_content = ""
    for p in paragraphs:
        p = p.strip()
        if p:
            # Escape XML chars? minimal replacement
            p = p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            body_content += f"{p}\n"
            
    # Wrap in a single section for now? 
    # The chunker splits by section, so if we only have one section it might try to chunk inside it.
    body = f"\n{body_content}\n"
    
    footer = ""
    
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
