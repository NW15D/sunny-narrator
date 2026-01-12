import re
from icecream import ic

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

        ic(len(body))
        return body, header, footer

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
