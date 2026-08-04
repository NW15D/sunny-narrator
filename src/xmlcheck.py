"""
XML validation utilities.

Provides FB2 XML validation using XSD schema and tag cleaning.
"""

import os
from lxml import etree


def ic(*args):
    """Debug print function (icecream replacement)."""
    if len(args) == 1:
        print(args[0])
    else:
        print(args)


def rem_tags(xml_string: str) -> str:
    """
    Parses and cleans up XML tags, ensuring structure validity for FB2 <section>.
    Uses lxml with recovery to fix unclosed tags and enforces FB2-compliant tags.
    
    Args:
        xml_string: XML string to clean
        
    Returns:
        Cleaned XML string
    """
    if not xml_string:
        return ""

    # FB2 Whitelist
    ALLOWED_BLOCK_TAGS = {
        'p', 'poem', 'subtitle', 'cite', 'empty-line', 'table', 
        'title', 'epigraph', 'annotation', 'section', 'image',
        'stanza', 'v', 'text-author', 'tr', 'th', 'td'
    }
    ALLOWED_INLINE_TAGS = {
        'strong', 'emphasis', 'style', 'a', 'strikethrough', 
        'sub', 'sup', 'code', 'image'
    }
    
    # Mapping for common malformed or non-FB2 tags
    TAG_MAPPING = {
        'b': 'strong',
        'i': 'emphasis',
        'em': 'emphasis',
        'italic': 'emphasis',
        'bold': 'strong',
        'u': 'emphasis',
    }

    try:
        # Use recovery parser to fix unclosed tags
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        
        # Ensure we have a single root for parsing
        # Always wrap in a container to handle multiple root elements
        xml_string = xml_string.strip()
        wrapped_xml = f"<section>{xml_string}</section>"

        # Parse
        root = etree.fromstring(wrapped_xml.encode('utf-8'), parser)
        
        if root is None:
            return xml_string

        def clean_node(node, is_block_level=False):
            """Recursively cleans a node and its children."""
            # 1. Clean children
            for child in node.getchildren():
                # Get local name (strip namespace)
                tag = child.tag
                if isinstance(tag, str):
                    if '}' in tag:
                        tag = tag.split('}', 1)[1]
                    tag = tag.lower()
                else:
                    tag = None
                
                if not tag:
                    continue

                # Map tags
                if tag in TAG_MAPPING:
                    child.tag = TAG_MAPPING[tag]
                    tag = child.tag

                # Check whitelist
                is_allowed = False
                if is_block_level:
                    if tag in ALLOWED_BLOCK_TAGS:
                        is_allowed = True
                else:
                    if tag in ALLOWED_INLINE_TAGS:
                        is_allowed = True

                if not is_allowed:
                    # Recurse into grandchildren before stripping the tag
                    clean_node(child, is_block_level)

                    # Strip tag but keep content and children
                    parent = node
                    index = parent.index(child)
                    
                    text = child.text or ""
                    tail = child.tail or ""
                    
                    # 1. Move children of 'child' to 'parent'
                    for i, grandchild in enumerate(list(child)):
                        parent.insert(index + i, grandchild)
                    
                    # 2. Merge text
                    if index == 0:
                        parent.text = (parent.text or "") + text
                    else:
                        parent[index-1].tail = (parent[index-1].tail or "") + text
                    
                    # 3. Merge tail
                    if len(child) > 0:
                        parent[index + len(child) - 1].tail = (parent[index + len(child) - 1].tail or "") + tail
                    else:
                        if index == 0:
                            parent.text = (parent.text or "") + tail
                        else:
                            parent[index-1].tail = (parent[index-1].tail or "") + tail
                    
                    parent.remove(child)
                else:
                    # Recurse
                    next_is_block = tag in {'section', 'cite', 'poem', 'annotation', 'epigraph', 'title', 'stanza', 'table', 'tr'}
                    clean_node(child, next_is_block)

            # 2. Post-process block level nodes to wrap raw text in <p>
            if is_block_level or node.tag == 'section':
                if node.text and node.text.strip():
                    new_p = etree.Element('p')
                    new_p.text = node.text
                    node.insert(0, new_p)
                    node.text = None

                for child in list(node):
                    if child.tail and child.tail.strip():
                        new_p = etree.Element('p')
                        new_p.text = child.tail
                        child.addnext(new_p)
                        child.tail = None

        # Start cleaning from root
        clean_node(root, is_block_level=True)

        # Serialize back to string
        cleaned_xml = etree.tostring(root, encoding='unicode', method='xml')
        
        # Remove the outer wrapper <section>...</section> we added
        cleaned_xml = cleaned_xml.strip()
        if cleaned_xml.startswith('<section>') and cleaned_xml.endswith('</section>'):
            cleaned_xml = cleaned_xml[9:-10]  # Remove <section> and </section>
        
        return cleaned_xml.strip()

    except Exception as e:
        ic(f"Error in rem_tags: {e}")
        return xml_string


def validate_fb2(xml_string: str) -> list:
    """
    Validates the FB2 XML string using lxml and the local XSD schema.
    
    Args:
        xml_string: FB2 XML string to validate
        
    Returns:
        List of error strings with line numbers. Empty list if valid.
    """
    errors = []
    try:
        # Load XSD Schema
        base_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(base_dir, 'schemas', 'FictionBook.xsd')
        
        if not os.path.exists(schema_path):
            return [f"Schema file not found at: {schema_path}"]

        xml_schema_doc = etree.parse(schema_path)
        xml_schema = etree.XMLSchema(xml_schema_doc)

        # Parse XML string
        parser = etree.XMLParser(recover=False)
        doc = etree.fromstring(xml_string.encode('utf-8'), parser)
        
        # Validate against schema
        if not xml_schema.validate(doc):
            for error in xml_schema.error_log:
                 errors.append(f"Line {error.line}, Column {error.column}: {error.message}")
        
    except etree.XMLSyntaxError as e:
        for error in e.error_log:
            errors.append(f"Line {error.line}, Column {error.column}: {error.message}")
            
    except Exception as e:
        errors.append(f"General Validation Error: {str(e)}")
        
    return errors
