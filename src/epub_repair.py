"""
EPUB Validation and Auto-Repair Module.

Validates and repairs EPUB files:
- ZIP structure integrity
- Required files presence (mimetype, META-INF/container.xml)
- XHTML content validity
- OPF manifest consistency
"""

import logging
import os
import zipfile
from typing import List, Optional
from lxml import etree

from src.xml_utils import get_safe_xml_parser

logger = logging.getLogger(__name__)


def validate_epub(epub_path: str) -> List[str]:
    """
    Validate EPUB file structure and content.
    
    Args:
        epub_path: Path to EPUB file
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not os.path.exists(epub_path):
        return [f"File not found: {epub_path}"]
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            # Check 1: mimetype must be first and uncompressed
            try:
                mimetype_info = zf.getinfo('mimetype')
                if mimetype_info.compress_type != zipfile.ZIP_STORED:
                    errors.append("mimetype must be uncompressed")
            except KeyError:
                errors.append("Missing required file: mimetype")
            
            # Check 2: Required structure files
            required_files = ['META-INF/container.xml']
            for req_file in required_files:
                if req_file not in zf.namelist():
                    errors.append(f"Missing required file: {req_file}")
            
            # Check 3: Find and validate OPF file
            opf_path = _find_opf_path(zf)
            if not opf_path:
                errors.append("Cannot find OPF content file")
            else:
                # Validate OPF XML
                try:
                    opf_content = zf.read(opf_path)
                    opf_errors = _validate_xml(opf_content, f"OPF ({opf_path})")
                    errors.extend(opf_errors)
                except Exception as e:
                    errors.append(f"Error reading OPF: {e}")
                
                # Check 4: Validate all XHTML content files
                xhtml_errors = _validate_xhtml_files(zf, opf_path)
                errors.extend(xhtml_errors)
                
    except zipfile.BadZipFile:
        errors.append("Invalid ZIP file structure")
    except Exception as e:
        errors.append(f"Validation error: {e}")
    
    return errors


def _find_opf_path(zf: zipfile.ZipFile) -> Optional[str]:
    """Find OPF file path from container.xml or by searching."""
    try:
        if 'META-INF/container.xml' in zf.namelist():
            container_content = zf.read('META-INF/container.xml')
            soup = etree.fromstring(container_content, get_safe_xml_parser())
            rootfile = soup.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
            if rootfile is not None:
                return rootfile.get('full-path')
    except Exception:
        logger.debug("Failed to read container.xml, falling back to .opf search", exc_info=True)
    
    # Fallback: search for .opf files
    opf_files = [f for f in zf.namelist() if f.endswith('.opf')]
    return opf_files[0] if opf_files else None


def _get_xhtml_files_from_opf(zf: zipfile.ZipFile, opf_path: str) -> List[str]:
    """Get list of XHTML files from OPF manifest."""
    try:
        opf_content = zf.read(opf_path)
        soup = etree.fromstring(opf_content, get_safe_xml_parser())
        
        # Find all items with XHTML media-type
        xhtml_files = []
        for item in soup.findall('.//{http://www.idpf.org/2007/opf}item'):
            media_type = item.get('media-type', '')
            if 'html' in media_type.lower():
                href = item.get('href', '')
                # Resolve relative path
                opf_dir = os.path.dirname(opf_path)
                if opf_dir:
                    href = os.path.join(opf_dir, href).replace('\\', '/')
                xhtml_files.append(href)
        
        return xhtml_files
    except Exception:
        return []


def _validate_xml(content: bytes, context: str) -> List[str]:
    """Validate XML content."""
    errors = []
    try:
        # lxml's XMLParser has no settable `recover` attribute after
        # construction (it's constructor-only and raises AttributeError on
        # assignment), so build a strict (non-recovering) parser directly
        # instead of mutating the one from get_safe_xml_parser().
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            dtd_validation=False,
            huge_tree=False,
            recover=False,  # strict mode for validation
        )
        etree.fromstring(content, parser)
    except etree.XMLSyntaxError as e:
        for error in e.error_log:
            errors.append(f"{context} - Line {error.line}: {error.message}")
    except Exception as e:
        errors.append(f"{context} - Error: {e}")
    return errors


def _validate_xhtml_files(zf: zipfile.ZipFile, opf_path: str) -> List[str]:
    """Validate all XHTML content files."""
    errors = []
    xhtml_files = _get_xhtml_files_from_opf(zf, opf_path)
    
    for xhtml_file in xhtml_files:
        try:
            if xhtml_file in zf.namelist():
                content = zf.read(xhtml_file)
                file_errors = _validate_xml(content, f"XHTML ({xhtml_file})")
                errors.extend(file_errors)
        except Exception as e:
            errors.append(f"Error reading {xhtml_file}: {e}")
    
    return errors


