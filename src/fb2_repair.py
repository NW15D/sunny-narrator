"""
FB2 XML Auto-Repair Module.

Fixes structural damage in an assembled FB2 without ever dropping text:
- BOM, junk after </FictionBook>, missing </FictionBook>
- missing XML declaration / namespace / <body>
- unbalanced tags inside every <body>, fixed at the place where they break
  (see fb2_structure.repair_fragment), not by piling closers at the end

Two earlier techniques were removed because they lost content: re-serialising
through lxml's recover=True parser (silently drops whatever it cannot parse)
and appending every missing </section> just before </body>.

A repair is only accepted if the book text is unchanged; repair_if_needed
additionally requires the result to be well-formed and, if the input already
was, to have fewer schema errors.
"""

import logging
import re
from typing import List, Tuple

from lxml import etree

from src.fb2_structure import repair_fragment, visible_text

logger = logging.getLogger(__name__)

_BODY_RE = re.compile(r'(<body\b[^>]*>)(.*?)(?:</body>|(?=<body\b|</FictionBook>)|\Z)', re.DOTALL)


def repair_fb2(xml_string: str) -> Tuple[str, List[str]]:
    """
    Automatically repair common FB2 XML errors.

    Args:
        xml_string: FB2 XML string to repair

    Returns:
        Tuple of (repaired_xml, list_of_repairs_made). If a repair would have
        changed the book text the original is returned untouched.
    """
    original = xml_string
    repairs = []

    if xml_string.startswith('\ufeff'):
        xml_string = xml_string[1:]
        repairs.append("Removed BOM")

    for step in (_remove_extra_content, _ensure_complete_root,
                 _repair_bodies, _ensure_fb2_structure):
        xml_string, repair = step(xml_string)
        if repair:
            repairs.append(repair)

    if _book_text(xml_string) != _book_text(original):
        logger.warning("FB2 repair rejected: it would have changed the book text")
        return original, ["Repair rejected: it would have changed the book text"]

    if repairs:
        repairs.insert(0, f"FB2 auto-repair completed: {len(repairs)} fix(es) applied")

    return xml_string, repairs


def _book_text(xml_string: str) -> str:
    """Visible text up to the end of the root element (junk after it is dropped
    on purpose). <binary> payloads are skipped: repair never touches them and
    they are most of an illustrated book."""
    end = xml_string.find('</FictionBook>')
    text = xml_string[:end] if end != -1 else xml_string
    return visible_text(re.sub(r'<binary\b[^>]*>.*?</binary>', '', text, flags=re.DOTALL))


def _well_formed(xml_string: str) -> bool:
    parser = etree.XMLParser(recover=False, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        etree.fromstring(xml_string.encode('utf-8'), parser)
        return True
    except (etree.XMLSyntaxError, ValueError):
        return False


def _remove_extra_content(xml_string: str) -> Tuple[str, str]:
    """Remove content after </FictionBook>."""
    end = xml_string.find('</FictionBook>')
    if end != -1:
        end += len('</FictionBook>')
        if xml_string[end:].strip():
            return xml_string[:end], "Removed extra content after </FictionBook>"
    return xml_string, ""


def _ensure_complete_root(xml_string: str) -> Tuple[str, str]:
    """Ensure FictionBook root element is properly closed."""
    if '<FictionBook' not in xml_string:
        return xml_string, ""

    open_count = len(re.findall(r'<FictionBook\b[^>]*>', xml_string))
    close_count = len(re.findall(r'</FictionBook>', xml_string))

    if open_count > close_count:
        xml_string = xml_string.rstrip() + '\n</FictionBook>'
        return xml_string, f"Added missing </FictionBook> (had {close_count}, needed {open_count})"

    return xml_string, ""


def _repair_bodies(xml_string: str) -> Tuple[str, str]:
    """Rebalance the content of every <body> and make sure each one is closed."""
    fixed = 0

    def fix(m: 're.Match') -> str:
        nonlocal fixed
        open_tag, inner = m.group(1), m.group(2)
        repaired = repair_fragment(inner, keep_sections=True, strip_unknown=False)
        if repaired != inner or not m.group(0).endswith('</body>'):
            fixed += 1
        return f'{open_tag}{repaired}</body>'

    result = _BODY_RE.sub(fix, xml_string)
    if fixed:
        return result, f"Rebalanced tags in {fixed} <body> element(s)"
    return xml_string, ""


def _ensure_fb2_structure(xml_string: str) -> Tuple[str, str]:
    """Ensure required FB2 structure elements exist."""
    repairs = []

    if not xml_string.startswith('<?xml'):
        xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string
        repairs.append("Added XML declaration")

    root = re.search(r'<FictionBook\b([^>]*)>', xml_string)
    if root and 'xmlns=' not in root.group(1):
        attrs = ' xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
        if 'xmlns:l=' not in root.group(1):
            attrs += ' xmlns:l="http://www.w3.org/1999/xlink"'
        xml_string = (xml_string[:root.start()] + '<FictionBook' + attrs + root.group(1) + '>'
                      + xml_string[root.end():])
        repairs.append("Added FictionBook namespace")

    if '<body>' not in xml_string and '<body ' not in xml_string:
        desc_end = xml_string.find('</description>')
        if desc_end != -1:
            insert_pos = desc_end + len('</description>')
            xml_string = xml_string[:insert_pos] + '\n<body>\n</body>' + xml_string[insert_pos:]
            repairs.append("Added missing <body> element")

    if repairs:
        return xml_string, "; ".join(repairs)
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


def repair_if_needed(xml_string: str, errors: List[str] = None) -> Tuple[str, List[str]]:
    """
    Repair a finished book only if it fails validation (text is always
    preserved, see repair_fb2). The result is kept only if it is well-formed
    XML and either the input was not, or the schema error count went down.
    Error counts alone are not comparable across that line: lxml stops at
    the first syntax error, so a broken file can report fewer errors than a
    readable one.

    Args:
        xml_string: The finished FB2
        errors: validate_fb2(xml_string), if the caller already has it

    Returns:
        Tuple of (xml, messages). xml is the input unchanged when it is
        already valid or when repairing did not help.
    """
    if errors is None:
        errors = validate_after_repair(xml_string)
    if not errors:
        return xml_string, []

    repaired, repairs = repair_fb2(xml_string)
    if repaired == xml_string:
        return xml_string, repairs
    if not _well_formed(repaired):
        return xml_string, ["Repair discarded: the result is not well-formed XML"]

    new_errors = validate_after_repair(repaired)
    if len(new_errors) < len(errors) or not _well_formed(xml_string):
        return repaired, repairs + [f"Validation errors: {len(errors)} -> {len(new_errors)}"]
    return xml_string, [f"Repair discarded: {len(errors)} errors before, {len(new_errors)} after"]
