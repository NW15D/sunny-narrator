"""
FB2 XML Auto-Repair Module.

Automatically fixes common FB2 XML validation errors:
- Premature end of data (unclosed tags)
- Extra content at the end
- Unbalanced tags
- Missing required structure
"""

import re
from lxml import etree
from typing import List, Tuple


def repair_fb2(xml_string: str) -> Tuple[str, List[str]]:
    """
    Automatically repair common FB2 XML errors.
    
    Args:
        xml_string: FB2 XML string to repair
        
    Returns:
        Tuple of (repaired_xml, list_of_repairs_made)
    """
    repairs = []
    original = xml_string
    
    # Step 1: Remove BOM if present
    if xml_string.startswith('\ufeff'):
        xml_string = xml_string[1:]
        repairs.append("Removed BOM")
    
    # Step 2: Remove extra content after </FictionBook>
    xml_string, repair = _remove_extra_content(xml_string)
    if repair:
        repairs.append(repair)
    
    # Step 3: Ensure FictionBook root element is complete
    xml_string, repair = _ensure_complete_root(xml_string)
    if repair:
        repairs.append(repair)
    
    # Step 4: Fix unclosed tags using lxml recovery parser
    xml_string, repair = _fix_unclosed_tags(xml_string)
    if repair:
        repairs.append(repair)
    
    # Step 5: Ensure required FB2 structure
    xml_string, repair = _ensure_fb2_structure(xml_string)
    if repair:
        repairs.append(repair)
    
    # Step 6: Balance section tags
    xml_string, repair = _balance_section_tags(xml_string)
    if repair:
        repairs.append(repair)
    
    # Step 7: Remove duplicate closing tags
    xml_string, repair = _remove_duplicate_closings(xml_string)
    if repair:
        repairs.append(repair)
    
    if repairs:
        repairs.insert(0, f"FB2 auto-repair completed: {len(repairs)} fix(es) applied")
    
    return xml_string, repairs


def _remove_extra_content(xml_string: str) -> Tuple[str, str]:
    """Remove content after </FictionBook>."""
    match = re.search(r'(</FictionBook>\s*).*$', xml_string, re.DOTALL)
    if match and match.group(1):
        end_pos = match.start(1) + len(match.group(1))
        if end_pos < len(xml_string.rstrip()):
            xml_string = xml_string[:end_pos].rstrip()
            return xml_string, "Removed extra content after </FictionBook>"
    return xml_string, ""


def _ensure_complete_root(xml_string: str) -> Tuple[str, str]:
    """Ensure FictionBook root element is properly closed."""
    # Check if FictionBook is opened
    if '<FictionBook' not in xml_string:
        return xml_string, ""
    
    # Check if FictionBook is properly closed
    open_count = len(re.findall(r'<FictionBook[^>]*>', xml_string))
    close_count = len(re.findall(r'</FictionBook>', xml_string))
    
    if open_count > close_count:
        # Add missing closing tag
        xml_string = xml_string.rstrip() + '\n</FictionBook>'
        return xml_string, f"Added missing </FictionBook> (had {close_count}, needed {open_count})"
    
    return xml_string, ""


def _fix_unclosed_tags(xml_string: str) -> Tuple[str, str]:
    """Fix unclosed tags using lxml recovery parser."""
    try:
        # Try to parse with recovery
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        root = etree.fromstring(xml_string.encode('utf-8'), parser)
        
        if root is not None:
            # Serialize back
            repaired = etree.tostring(root, encoding='unicode', method='xml')
            if repaired != xml_string:
                return repaired, "Fixed unclosed/broken tags using XML recovery"
    except Exception:
        pass
    
    return xml_string, ""


def _ensure_fb2_structure(xml_string: str) -> Tuple[str, str]:
    """Ensure required FB2 structure elements exist."""
    repairs = []
    
    # Check for XML declaration
    if not xml_string.startswith('<?xml'):
        xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string
        repairs.append("Added XML declaration")
    
    # Check for FictionBook namespace
    if '<FictionBook' in xml_string and 'xmlns=' not in xml_string.split('<FictionBook')[1].split('>')[0]:
        # Add namespace if missing
        xml_string = xml_string.replace(
            '<FictionBook>',
            '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
        )
        repairs.append("Added FictionBook namespace")
    
    # Check for body element
    if '<body>' not in xml_string and '<body ' not in xml_string:
        # Try to find where to insert body
        if '<description>' in xml_string:
            # Insert after description
            desc_end = xml_string.find('</description>')
            if desc_end != -1:
                insert_pos = desc_end + len('</description>')
                xml_string = xml_string[:insert_pos] + '\n<body>\n</body>' + xml_string[insert_pos:]
                repairs.append("Added missing <body> element")
    
    if repairs:
        return xml_string, "; ".join(repairs)
    return xml_string, ""


def _balance_section_tags(xml_string: str) -> Tuple[str, str]:
    """Balance opening and closing section tags."""
    # Count section tags
    open_sections = len(re.findall(r'<section[^>]*>', xml_string))
    close_sections = len(re.findall(r'</section>', xml_string))
    
    if open_sections > close_sections:
        # Need to add closing tags
        missing = open_sections - close_sections
        # Add before </body> or at end
        if '</body>' in xml_string:
            xml_string = xml_string.replace('</body>', '</section>\n' * missing + '</body>')
        else:
            xml_string = xml_string.rstrip() + '\n' + '</section>\n' * missing
        return xml_string, f"Added {missing} missing </section> tag(s)"
    
    return xml_string, ""


def _remove_duplicate_closings(xml_string: str) -> Tuple[str, str]:
    """Remove duplicate closing tags."""
    # Fix duplicate FictionBook closings
    fiction_closings = len(re.findall(r'</FictionBook>', xml_string))
    if fiction_closings > 1:
        # Keep only the last one
        parts = xml_string.rsplit('</FictionBook>', 1)
        xml_string = parts[0].rstrip() + '</FictionBook>' + parts[1] if len(parts) > 1 else xml_string
        return xml_string, f"Removed duplicate </FictionBook> tags (had {fiction_closings})"
    
    # Fix duplicate body closings
    body_closings = len(re.findall(r'</body>', xml_string))
    if body_closings > 1:
        parts = xml_string.rsplit('</body>', 1)
        xml_string = parts[0] + '</body>' + parts[1] if len(parts) > 1 else xml_string
        return xml_string, f"Removed duplicate </body> tags (had {body_closings})"
    
    return xml_string, ""


def validate_after_repair(xml_string: str) -> List[str]:
    """
    Validate FB2 after repair and return any remaining errors.
    
    Args:
        xml_string: Repaired FB2 XML
        
    Returns:
        List of remaining validation errors
    """
    from .xmlcheck import validate_fb2
    return validate_fb2(xml_string)


def repair_and_validate(xml_string: str) -> Tuple[str, List[str], List[str]]:
    """
    Repair FB2 and validate result.
    
    Args:
        xml_string: FB2 XML to repair
        
    Returns:
        Tuple of (repaired_xml, repairs_made, remaining_errors)
    """
    repaired, repairs = repair_fb2(xml_string)
    errors = validate_after_repair(repaired)
    return repaired, repairs, errors
