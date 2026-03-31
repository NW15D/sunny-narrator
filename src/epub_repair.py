"""
EPUB Validation and Auto-Repair Module.

Validates and repairs EPUB files:
- ZIP structure integrity
- Required files presence (mimetype, META-INF/container.xml)
- XHTML content validity
- OPF manifest consistency
"""

import os
import re
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional
from lxml import etree


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


def repair_epub(epub_path: str, output_path: Optional[str] = None, max_iterations: int = 3) -> Tuple[str, List[str]]:
    """
    Attempt to repair common EPUB errors.
    
    Args:
        epub_path: Path to EPUB file to repair
        output_path: Output path for repaired file (default: overwrite original)
        max_iterations: Maximum repair iterations to prevent infinite loops
        
    Returns:
        Tuple of (output_path, list_of_repairs_made)
    """
    repairs = []
    
    if output_path is None:
        output_path = epub_path
    
    temp_path = epub_path + '.repair.tmp'
    backup_path = epub_path + '.backup'
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf_in:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf_out:
                # Get list of files
                file_list = zf_in.namelist()
                
                # Repair 1: Ensure mimetype is first and uncompressed
                if 'mimetype' in file_list:
                    mimetype_content = zf_in.read('mimetype')
                    zf_out.writestr('mimetype', mimetype_content, compress_type=zipfile.ZIP_STORED)
                    repairs.append("Fixed mimetype compression (now uncompressed)")
                else:
                    # Add default mimetype
                    zf_out.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
                    repairs.append("Added missing mimetype file")
                
                # Repair 2: Ensure META-INF/container.xml exists
                if 'META-INF/container.xml' not in file_list:
                    # Find OPF file
                    opf_candidates = [f for f in file_list if f.endswith('.opf')]
                    if opf_candidates:
                        opf_path = opf_candidates[0]
                    else:
                        opf_path = 'content.opf'
                    
                    container_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>'''
                    zf_out.writestr('META-INF/container.xml', container_xml)
                    repairs.append("Added missing META-INF/container.xml")
                
                # Repair 3: Process and fix XHTML files
                opf_path = _find_opf_path(zf_in)
                xhtml_files = _get_xhtml_files_from_opf(zf_in, opf_path) if opf_path else []
                
                for file_name in file_list:
                    if file_name in ['mimetype', 'META-INF/container.xml']:
                        continue  # Already handled
                    
                    content = zf_in.read(file_name)
                    
                    # Fix XHTML files
                    if file_name.endswith(('.xhtml', '.html', '.htm')):
                        content, file_repairs = _repair_xhtml(content, file_name)
                        repairs.extend(file_repairs)
                    
                    zf_out.writestr(file_name, content)
        
        # Create backup before overwriting original
        if output_path == epub_path and os.path.exists(epub_path):
            os.replace(epub_path, backup_path)
        
        # Replace original with repaired
        if output_path == epub_path:
            os.replace(temp_path, epub_path)
        else:
            os.replace(temp_path, output_path)
        
        if repairs:
            repairs.insert(0, f"EPUB repair completed: {len([r for r in repairs if not r.startswith('EPUB')])} fix(es) applied")
        
        return output_path, repairs
        
    except Exception as e:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise Exception(f"EPUB repair failed: {e}")


def _find_opf_path(zf: zipfile.ZipFile) -> Optional[str]:
    """Find OPF file path from container.xml or by searching."""
    try:
        if 'META-INF/container.xml' in zf.namelist():
            container_content = zf.read('META-INF/container.xml')
            soup = etree.fromstring(container_content)
            rootfile = soup.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
            if rootfile is not None:
                return rootfile.get('full-path')
    except Exception:
        pass
    
    # Fallback: search for .opf files
    opf_files = [f for f in zf.namelist() if f.endswith('.opf')]
    return opf_files[0] if opf_files else None


def _get_xhtml_files_from_opf(zf: zipfile.ZipFile, opf_path: str) -> List[str]:
    """Get list of XHTML files from OPF manifest."""
    try:
        opf_content = zf.read(opf_path)
        soup = etree.fromstring(opf_content)
        
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
        parser = etree.XMLParser(recover=False)
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


def _repair_xhtml(content: bytes, file_name: str) -> Tuple[bytes, List[str]]:
    """Repair XHTML content."""
    repairs = []
    content_str = content.decode('utf-8', errors='replace')
    
    # Repair 1: Fix unclosed tags using lxml
    try:
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        root = etree.fromstring(content_str.encode('utf-8'), parser)
        
        if root is not None:
            repaired_content = etree.tostring(root, encoding='unicode', method='xml')
            if repaired_content != content_str:
                repairs.append(f"Fixed unclosed tags in {file_name}")
                content_str = repaired_content
    except Exception:
        pass  # If repair fails, keep original
    
    # Repair 2: Ensure proper XHTML namespace
    if '<html' in content_str and 'xmlns=' not in content_str.split('<html')[1].split('>')[0]:
        content_str = content_str.replace(
            '<html',
            '<html xmlns="http://www.w3.org/1999/xhtml"'
        )
        repairs.append(f"Added XHTML namespace to {file_name}")
    
    # Repair 3: Fix self-closing tags for XHTML
    content_str = re.sub(r'<(br|hr|img|input|meta|link)([^>]*[^/])>', r'<\1\2 />', content_str)
    
    # Repair 4: Ensure XML declaration
    if not content_str.startswith('<?xml'):
        content_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + content_str
        repairs.append(f"Added XML declaration to {file_name}")
    
    return content_str.encode('utf-8'), repairs


def validate_and_repair_epub(epub_path: str, output_path: Optional[str] = None, max_iterations: int = 3) -> Tuple[str, List[str], List[str]]:
    """
    Validate EPUB and repair if needed.
    
    Args:
        epub_path: Path to EPUB file
        output_path: Output path for repaired file (default: overwrite)
        max_iterations: Maximum repair iterations to prevent infinite loops
        
    Returns:
        Tuple of (output_path, repairs_made, remaining_errors)
    """
    all_repairs = []
    current_path = epub_path
    
    for iteration in range(max_iterations):
        # Validate
        errors = validate_epub(current_path)
        
        if not errors:
            if not all_repairs:
                return current_path, ["EPUB is valid"], []
            return current_path, all_repairs, []
        
        # Attempt repair
        current_path, repairs = repair_epub(current_path, output_path if iteration == 0 else None, max_iterations=1)
        all_repairs.extend(repairs)
        
        # Check if any repairs were made
        if len(repairs) <= 1:  # Only header message, no actual fixes
            break
    
    # Final validation
    remaining_errors = validate_epub(current_path)
    
    return current_path, all_repairs, remaining_errors
