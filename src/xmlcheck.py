"""
XML validation utilities.

Provides FB2 XML validation using XSD schema and tag cleaning.
"""

import os
from lxml import etree


# F2: XSD schema cache - FictionBook.xsd is static; parsing it on
# every validate_fb2 call wasted time on repeated validations.
_XSD_CACHE = {}


def _get_fb2_schema():
    """Lazily load and cache the FictionBook XSD schema.

    Returns:
        Tuple of (XMLSchema or None, schema_path).
    """
    if 'schema' not in _XSD_CACHE:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(base_dir, 'schemas', 'FictionBook.xsd')
        if os.path.exists(schema_path):
            _XSD_CACHE['schema'] = etree.XMLSchema(etree.parse(schema_path))
        else:
            _XSD_CACHE['schema'] = None
        _XSD_CACHE['path'] = schema_path
    return _XSD_CACHE['schema'], _XSD_CACHE['path']


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
        # Load XSD Schema (F2: cached - the XSD file is static)
        xml_schema, schema_path = _get_fb2_schema()
        if xml_schema is None:
            return [f"Schema file not found at: {schema_path}"]

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
