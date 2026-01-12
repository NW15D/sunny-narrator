from bs4 import BeautifulSoup
from lxml import etree
from icecream import ic

def rem_tags(xml_string):
    """
    Parses and cleans up XML tags, ensuring structure validity.
    Input is assumed to be the content of a <section> (or similar fragment).
    Wraps it in a dummy root, lets BS4 close tags, then unwraps.
    """
    # Wrap in dummy root to ensure parsability of fragments
    wrapped_xml = f"<root>{xml_string}</root>"
    
    # Use 'xml' parser for strict XML handling (requires lxml installed)
    soup = BeautifulSoup(wrapped_xml, 'xml')
    
    # BS4 automatically closes tags when parsing.
    # We just need to extract the inner content of <root>
    root = soup.find('root')
    
    if root:
        # decode_contents() returns the string representation of children
        cleaned_string = root.decode_contents()
        return cleaned_string.strip()
    
    return xml_string

import os

def validate_fb2(xml_string):
    """
    Validates the FB2 XML string using lxml and the local XSD schema.
    Returns a list of error strings with line numbers.
    If valid, returns an empty list.
    """
    errors = []
    try:
        # Load XSD Schema
        # Assuming schemas are in src/schemas relative to this file
        base_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(base_dir, 'schemas', 'FictionBook.xsd')
        
        if not os.path.exists(schema_path):
            return [f"Schema file not found at: {schema_path}"]

        xml_schema_doc = etree.parse(schema_path)
        xml_schema = etree.XMLSchema(xml_schema_doc)

        # Parse XML string
        parser = etree.XMLParser(recover=False) # strict parsing
        doc = etree.fromstring(xml_string.encode('utf-8'), parser)
        
        # Validate against schema
        if not xml_schema.validate(doc):
            for error in xml_schema.error_log:
                 errors.append(f"Line {error.line}, Column {error.column}: {error.message}")
        
    except etree.XMLSyntaxError as e:
        # Parsing error (malformed XML)
        for error in e.error_log:
            errors.append(f"Line {error.line}, Column {error.column}: {error.message}")
            
    except Exception as e:
        errors.append(f"General Validation Error: {str(e)}")
        
    return errors
