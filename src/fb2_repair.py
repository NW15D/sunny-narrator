"""
FB2 XML Auto-Repair Module.

Automatically fixes common FB2 XML validation errors:
- Premature end of data (unclosed tags)
- Extra content at the end
- Unbalanced tags
- Missing required structure
"""

import logging
import re
from lxml import etree
from typing import List, Tuple

from src.xml_utils import get_safe_xml_parser

logger = logging.getLogger(__name__)


def repair_fb2(xml_string: str, max_iterations: int = 3) -> Tuple[str, List[str]]:
    """
    Automatically repair common FB2 XML errors.
    
    Args:
        xml_string: FB2 XML string to repair
        max_iterations: Maximum repair iterations to prevent infinite loops
        
    Returns:
        Tuple of (repaired_xml, list_of_repairs_made)
    """
    repairs = []
    
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
        parser = get_safe_xml_parser()
        root = etree.fromstring(xml_string.encode('utf-8'), parser)
        
        if root is not None:
            # Serialize back
            repaired = etree.tostring(root, encoding='unicode', method='xml')
            if repaired != xml_string:
                return repaired, "Fixed unclosed/broken tags using XML recovery"
    except Exception:
        logger.debug("XML recovery parse failed, keeping original XML", exc_info=True)
    
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
    """Balance opening and closing section tags with depth tracking."""
    # Count section tags with depth tracking to handle nesting
    section_opens = list(re.finditer(r'<section[^>]*>', xml_string))
    section_closes = list(re.finditer(r'</section>', xml_string))
    
    open_count = len(section_opens)
    close_count = len(section_closes)
    
    if open_count > close_count:
        # Need to add closing tags - but be smart about placement
        missing = open_count - close_count
        
        # Track section depth to find proper insertion points
        opens_pos = [m.end() for m in section_opens]
        closes_pos = [m.start() for m in section_closes]
        
        # Simple depth calculation: count opens before each position
        def get_depth(pos):
            opens_before = sum(1 for p in opens_pos if p <= pos)
            closes_before = sum(1 for p in closes_pos if p <= pos)
            return opens_before - closes_before
        
        # Find positions where depth > 0 (inside unclosed sections)
        # Insert closing tags before </body> or at strategic points
        if '</body>' in xml_string:
            body_close_pos = xml_string.find('</body>')
            body_depth = get_depth(body_close_pos)
            
            # Only add as many as needed to balance at body level
            to_add = min(missing, body_depth)
            if to_add > 0:
                xml_string = xml_string.replace('</body>', '</section>\n' * to_add + '</body>')
                return xml_string, f"Added {to_add} missing </section> tag(s) before </body>"
        
        # Fallback: add at end if still unbalanced
        if missing > 0:
            xml_string = xml_string.rstrip() + '\n' + '</section>\n' * missing
            return xml_string, f"Added {missing} missing </section> tag(s) at end"
    
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


def repair_and_validate(xml_string: str, max_iterations: int = 3) -> Tuple[str, List[str], List[str]]:
    """
    Repair FB2 and validate result with iteration limit.
    
    Args:
        xml_string: FB2 XML to repair
        max_iterations: Maximum repair iterations to prevent infinite loops
        
    Returns:
        Tuple of (repaired_xml, repairs_made, remaining_errors)
    """
    all_repairs = []
    current = xml_string
    
    for iteration in range(max_iterations):
        repaired, repairs = repair_fb2(current, max_iterations=1)
        all_repairs.extend(repairs)
        
        # Check if any actual fixes were made
        actual_fixes = [r for r in repairs if not r.startswith("FB2 auto-repair")]
        if not actual_fixes:
            break
        
        current = repaired
    
    errors = validate_after_repair(current)
    return current, all_repairs, errors
