import re
from bs4 import BeautifulSoup
from icecream import ic
from src.config import Config

config = Config()

def parse_xml(file_path):
    """
    Parses an FB2 XML file and separates the header, body, and footer.
    Also handles some cleanup and injection of translator info.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        start_body = content.find('<body')
        end_body_tag = content.find('</body>')

        if start_body == -1 or end_body_tag == -1:
            raise ValueError("Body tag not found in the XML file")

        # Find the end of the opening <body> tag
        end_start_body = content.find('>', start_body) + 1
        end_body = end_body_tag

        header = content[:start_body]
        body = content[end_start_body:end_body]
        footer = content[end_body_tag + len('</body>'):]

        # Remove namespaces
        body = re.sub(r'\sxmlns="[^"]+"', '', body, count=1)
        body = re.sub(r'<myheader>.*?</myheader>', '', body, flags=re.DOTALL)
        body = re.sub(r'<myfooter>.*?</myfooter>', '', body, flags=re.DOTALL)
        
        # Add translator info to title-info
        header = re.sub(r'</title-info>',
                        '<translator><nickname>Sunny narrator opensource AI translator </nickname> <email>n@uwns.org</email> </translator> </title-info>',
                        header, flags=re.DOTALL)

        # Remove <myheader> and <myfooter> from header and footer
        header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
        footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)

        if config.debug:
            ic(len(body))
        return body, header, footer

def extract_metadata(header):
    """
    Extracts key metadata from the FB2 header using BeautifulSoup.
    """
    # We use 'xml' parser for FB2
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
        # Extract paragraphs as a list of strings
        paragraphs = [p.get_text() for p in annotation_tag.find_all('p')]
        # If no <p> tags, just get text
        if not paragraphs:
            paragraphs = [annotation_tag.get_text()]
        metadata['annotation'] = paragraphs
    else:
        metadata['annotation'] = []

    # Genres
    genres = [g.get_text() for g in title_info.find_all('genre')]
    metadata['genre'] = genres

    return metadata

def update_header_with_metadata(header, metadata):
    """
    Updates the FB2 header with translated metadata.
    """
    soup = BeautifulSoup(header, 'xml')
    title_info = soup.find('title-info')
    if not title_info:
        return header

    # Update Title
    if 'book-title' in metadata:
        title_tag = title_info.find('book-title')
        if title_tag:
            title_tag.string = metadata['book-title']
        else:
            new_title = soup.new_tag('book-title')
            new_title.string = metadata['book-title']
            title_info.append(new_title)

    # Update Authors
    if 'author' in metadata:
        # For authors, we might have multiple. 
        # Usually easier to replace existing author tags if we have translated ones.
        # But FB2 can have many authors. If the count matches, we replace.
        existing_authors = title_info.find_all('author')
        new_authors_data = metadata['author']
        
        for i, author_data in enumerate(new_authors_data):
            if i < len(existing_authors):
                author_tag = existing_authors[i]
                for tag_name, value in author_data.items():
                    tag = author_tag.find(tag_name)
                    if tag:
                        tag.string = value
                    else:
                        new_tag = soup.new_tag(tag_name)
                        new_tag.string = value
                        author_tag.append(new_tag)
            else:
                # Add new author if more than existing (unlikely in translation but possible)
                new_author_tag = soup.new_tag('author')
                for tag_name, value in author_data.items():
                    new_tag = soup.new_tag(tag_name)
                    new_tag.string = value
                    new_author_tag.append(new_tag)
                title_info.append(new_author_tag)

    # Update Series
    if 'sequence' in metadata:
        existing_sequences = title_info.find_all('sequence')
        for i, s_data in enumerate(metadata['sequence']):
            if i < len(existing_sequences):
                if 'name' in s_data:
                    existing_sequences[i]['name'] = s_data['name']
            # We don't usually translate sequence numbers

    # Update Annotation
    if 'annotation' in metadata:
        annotation_tag = title_info.find('annotation')
        if not annotation_tag:
            annotation_tag = soup.new_tag('annotation')
            title_info.append(annotation_tag)
        
        # Clear existing content
        annotation_tag.clear()
        for p_text in metadata['annotation']:
            p_tag = soup.new_tag('p')
            p_tag.string = p_text
            annotation_tag.append(p_tag)

    # Return as string, keeping the XML declaration if it was there?
    # BS4 might mess up the prefix or declaration.
    # Since 'header' is just a slice of the file, we return soup.decode()
    return str(soup)

def prepare_chunks(body, max_len_chunk):
    """
    Splits the body content into sections and chunks based on max_len_chunk.
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

        # Split the section into chunks
        chunk_start = 0
        while chunk_start < len(section):
            chunk_end = chunk_start + max_len_chunk
            if chunk_end >= len(section):
                chunk_end = len(section)
            else:
                # Find the nearest </p> tag within the chunk to avoid breaking paragraphs
                pos = section.rfind('</p>', chunk_start, chunk_end)
                if pos != -1:
                    chunk_end = pos + len('</p>')

            chunks.append(section[chunk_start:chunk_end])
            chunk_start = chunk_end

        sections.append(chunks)
        start = section_end + len('</section>')

    return sections

def get_cover_image(header, footer):
    """
    Extracts the cover image base64 data from the footer based on header info.
    Returns the base64 string or None if not found.
    """
    # 1. Find image href in header <coverpage><image l:href="#..."/>
    cover_match = re.search(r'<coverpage>\s*<image[^>]*l:href=["\']#?([^"\']+)["\'][^>]*/>\s*</coverpage>', header)
    if not cover_match:
        # Try simplified search without coverpage tag constraint, just first image in title-info?
        # But standard is coverpage.
        return None

    image_id = cover_match.group(1)
    
    # 2. Find binary block in footer <binary id="...">...</binary>
    # Note: id in binary might not have #, but href does.
    # Regex to find binary with id
    binary_pattern = fr'<binary[^>]*id="{re.escape(image_id)}"[^>]*>(.*?)</binary>'
    binary_match = re.search(binary_pattern, footer, re.DOTALL)
    
    if binary_match:
        return binary_match.group(1)
    
    return None

def replace_cover_image(header, footer, body, new_content):
    """
    Replaces the cover image with new content (image or text).
    Returns updated (header, footer, body) tuple.
    """
    # Check if new_content looks like base64 (no spaces, long string) or text
    # Simple heuristic: if it contains spaces and is not huge block of chars, it's text.
    # Or check if it validates as base64? 
    # Let's assume if it starts with "data:image" or is just pure base64 chars without spaces it's image.
    # But usually, the API returns what we asked.
    
    is_image = False
    if len(new_content) > 100 and " " not in new_content[:100]:
        is_image = True
    
    # Locate the cover image ID
    cover_match = re.search(r'<coverpage>\s*<image[^>]*l:href=["\']#?([^"\']+)["\'][^>]*/>\s*</coverpage>', header)
    if not cover_match:
        # No cover found, nothing to replace? Or should we insert?
        # For now, only replace if exists.
        return header, footer, body

    image_id = cover_match.group(1)
    
    if is_image:
        # Replace binary content
        binary_pattern = fr'(<binary[^>]*id="{re.escape(image_id)}"[^>]*>)(.*?)(</binary>)'
        # We assume new_content is just the base64 data (without data:image prefix if present, we should strip it?)
        # Base64 from OpenAI might be raw.
        # Ensure we strip possible data URI scheme
        if new_content.startswith('data:image'):
            new_content = new_content.split(',', 1)[1]
            
        footer = re.sub(binary_pattern, fr'\1{new_content}\3', footer, count=1, flags=re.DOTALL)
        
    else:
        # It is text description
        # 1. Remove coverpage from header
        header = re.sub(r'<coverpage>.*?</coverpage>', '', header, flags=re.DOTALL)
        
        # 2. Remove binary from footer (optional, to save space)
        binary_pattern = fr'<binary[^>]*id="{re.escape(image_id)}"[^>]*>.*?</binary>'
        footer = re.sub(binary_pattern, '', footer, flags=re.DOTALL)
        
        # 3. Add text to body
        # Insert at the beginning of the body
        # Check if body has a section, insert before or inside first section?
        # Or add to annotation in header? 
        # User request: "замену ее в теле книги на полуенный результат" -> "replace it in the book body with the received result"
        # Since it's text, adding it as a <p> or <section> at start of body is appropriate.
        
        new_text_block = f'<section><title><p>Cover Description</p></title><p>{new_content}</p></section>'
        
        # Insert after <body ...>
        # Find first occurrence of > after <body
        body_start = body.find('>') + 1
        body = body[:body_start] + '\n' + new_text_block + body[body_start:]
        
    return header, footer, body
