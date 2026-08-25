"""
Calibre Pipeline - Convert EPUB/FB2 to Markdown and translate using Calibre.

This module provides functions to:
1. Convert EPUB/FB2 to Markdown using Calibre (ebook-convert)
2. Translate Markdown in chunks using existing translate_chunk
3. Build output FB2/EPUB from translated Markdown
"""

__all__ = [
    'convert_to_markdown',
    'translate_chunks',
    'build_output',
    'run_pipeline',
    'check_calibre_installed',
    'TempDir',
    'TranslationStats',
    'ValidationIssue',
    'ValidationReport',
    'validate_epub',
    'validate_fb2',
    'validate_output',
    'extract_dictionary_from_md',
    'save_dictionary',
]

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

try:
    import pypandoc
    PANDOC_AVAILABLE = True
except ImportError:
    PANDOC_AVAILABLE = False
    pypandoc = None

# Import existing utilities
from src.utils import split_text_smartly, config, validate_translation_length, _pipeline, translate_chunk
from src.checkpoint_manager import CheckpointManager
from src import markdown_utils
from src.markdown_utils import split_markdown_by_size, sanitize_surrogates

# Precompiled Calibre-specific cleanup patterns (narrowed to avoid removing valid Pandoc attributes)
_RE_CALIBRE_COMMENT = re.compile(r'<!--\s*\d+\s*-->')
_RE_CALIBRE_SECTION_FULL = re.compile(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_CLASS = re.compile(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_BARE = re.compile(r'<[^>]*>:::</[^>]*>', re.DOTALL)
# Only match standalone ::: not part of fenced div syntax (e.g. ::: {.class})
_RE_CALIBRE_TRIPLE_COLON = re.compile(r':::(?!\s*\{)')
_RE_CALIBRE_PARA = re.compile(r'<p>\s*\{#calibre[^}]*\}\s*</p>', re.DOTALL)
_RE_CALIBRE_ANCHOR = re.compile(r'\{#calibre[^}]*\}')  # Only calibre-specific anchors
_RE_CALIBRE_CLASS = re.compile(r'\{\.calibre\d*\}')  # Only calibre-specific classes
_RE_CALIBRE_ID_ATTR = re.compile(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', re.IGNORECASE)
_RE_CALIBRE_CLASS_ATTR = re.compile(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', re.IGNORECASE)
# Only match --- that is a standalone line (not setext H2 underline, not pipe table separator)
# Must be preceded by \n\n (blank line) to avoid destroying headings and tables
_RE_HR_MARKERS = re.compile(r'(?<=\n\n)---\s*\n')
_RE_MULTI_BLANK = re.compile(r'\n{3,}')
# Markdown image syntax: ![alt](path "optional title")
_RE_MD_IMAGE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
_IMG_PLACEHOLDER_FMT = '⁣IMGREF{}⁣'  # invisible-separator wrapper the LLM has no reason to translate
# C3 fix: <img src="images/foo.jpg"> -> <img src="foo.jpg"> — book images are
# copied to the HTML's own temp dir (root), not into an images/ subdirectory,
# so ebook-convert needs the bare filename to find them.
_RE_IMG_SRC = re.compile(
    r'(<img[^>]*\bsrc=["\'])(?:images/)?([^/"\'\s>]+)(["\'])',
    re.IGNORECASE
)

@dataclass
class TranslationStats:
    """Aggregate counters from a translate_chunks() run.

    translate_chunks previously computed total_source_len/total_target_len/
    failed_chunks locally and threw them away once translation finished
    (they were only persisted inside checkpoint payloads, which vanish once
    checkpoint_mgr.remove() runs). Passing a TranslationStats instance via
    stats_out lets run_pipeline() surface the same numbers the classic FB2
    pipeline already prints via print_translation_report().
    """
    total_source_len: int = 0
    total_target_len: int = 0
    total_chunks: int = 0
    failed_chunks: int = 0


@dataclass
class ValidationIssue:
    """Single validation issue found during output file validation."""
    severity: str  # "error" or "warning"
    message: str
    details: str = ""
    file_line: int = 0


@dataclass
class ValidationReport:
    """Validation result report for output file."""
    is_valid: bool = False
    file_path: str = ""
    file_size: int = 0
    format: str = ""
    issues: List[ValidationIssue] = field(default_factory=list)

    def add_issue(self, severity: str, message: str, details: str = "", line: int = 0):
        """Add an issue to the report."""
        self.issues.append(ValidationIssue(severity, message, details, line))

    def has_errors(self) -> bool:
        """Check if report has any errors (not warnings)."""
        return any(issue.severity == "error" for issue in self.issues)

    def summary(self) -> str:
        """Return human-readable summary of validation results."""
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        status = "PASS" if self.is_valid else "FAIL"
        return (
            f"Validation {status}: {self.file_path} "
            f"({self.file_size} bytes, {self.format}) — "
            f"{errors} error(s), {warnings} warning(s)"
        )


logger = None


def _init_logger():
    """Lazy import of logger to avoid circular imports."""
    global logger
    if logger is None:
        try:
            import logging
            logger = logging.getLogger(__name__)
        except ImportError:
            import logging
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger(__name__)


class TempDir:
    """Context manager for temporary directory cleanup."""
    
    def __init__(self, prefix: str = "calibre_"):
        self.path: Optional[str] = None
        self.prefix = prefix
    
    def __enter__(self) -> str:
        self.path = tempfile.mkdtemp(prefix=self.prefix)
        return self.path
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path and os.path.exists(self.path):
            shutil.rmtree(self.path)
        return False


def _run_command(cmd: list, timeout: int = 300) -> subprocess.CompletedProcess:
    """
    Run a shell command and return the result.
    
    Args:
        cmd: Command as list of strings
        timeout: Timeout in seconds
        
    Returns:
        CompletedProcess instance
        
    Raises:
        FileNotFoundError: If command is not found
        subprocess.CalledProcessError: If command fails
        subprocess.TimeoutExpired: If command times out
    """
    _init_logger()
    logger.info(f"Running: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True
    )


def check_calibre_installed() -> bool:
    """
    Check if Calibre (ebook-convert) is installed and available.
    
    Returns:
        True if Calibre is installed, False otherwise
    """
    try:
        result = subprocess.run(
            ["ebook-convert", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def extract_metadata_from_opf(opf_content: str) -> dict:
    """
    Extract metadata from OPF file content.
    
    Args:
        opf_content: Content of the OPF file
        
    Returns:
        Dictionary with metadata fields
    """
    metadata = {
        "title": "",
        "author": "",
        "language": "",
        "publisher": "",
        "isbn": "",
        "description": ""
    }
    
    # Extract title
    title_match = re.search(r'<dc:title[^>]*>([^<]+)</dc:title>', opf_content, re.IGNORECASE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()
    
    # Extract author
    author_match = re.search(r'<dc:creator[^>]*>([^<]+)</dc:creator>', opf_content, re.IGNORECASE)
    if author_match:
        metadata["author"] = author_match.group(1).strip()
    
    # Extract language
    lang_match = re.search(r'<dc:language[^>]*>([^<]+)</dc:language>', opf_content, re.IGNORECASE)
    if lang_match:
        metadata["language"] = lang_match.group(1).strip()
    
    # Extract publisher
    pub_match = re.search(r'<dc:publisher[^>]*>([^<]+)</dc:publisher>', opf_content, re.IGNORECASE)
    if pub_match:
        metadata["publisher"] = pub_match.group(1).strip()
    
    # Extract ISBN (M10: validate format — only accept ISBN-10 or ISBN-13 patterns)
    isbn_match = re.search(r'<dc:identifier[^>]*>([^<]+)</dc:identifier>', opf_content, re.IGNORECASE)
    if isbn_match:
        raw_isbn = isbn_match.group(1).strip()
        # Strip common prefixes and hyphens
        isbn_clean = re.sub(r'^urn:isbn:', '', raw_isbn, flags=re.IGNORECASE).replace('-', '').strip()
        if re.match(r'^(?:\d{9}[\dXx]|\d{13})$', isbn_clean):
            metadata["isbn"] = raw_isbn
    
    # M11: decode HTML entities in all metadata fields
    import html as _html_dec
    for key in metadata:
        if isinstance(metadata[key], str):
            metadata[key] = _html_dec.unescape(metadata[key])
    
    # Extract description
    desc_match = re.search(r'<dc:description[^>]*>([^<]+)</dc:description>', opf_content, re.IGNORECASE)
    if desc_match:
        metadata["description"] = desc_match.group(1).strip()
    
    return metadata


def convert_to_markdown(input_path: str) -> tuple[str, dict]:
    """
    Convert EPUB/FB2 to Markdown using Calibre.
    
    This function:
    1. Validates Calibre is installed
    2. Converts input to HTMLZ using Calibre ebook-convert
    3. Extracts HTML from HTMLZ archive
    4. Converts HTML to Markdown using pypandoc
    5. Cleans Calibre-specific markers
    6. Extracts metadata from OPF
    7. Cleans up temporary files
    
    Args:
        input_path: Path to EPUB or FB2 file
        
    Returns:
        Tuple of (markdown_text, metadata_dict)
        
    Raises:
        FileNotFoundError: If Calibre is not installed or input file not found
        ValueError: If conversion fails
    """
    _init_logger()
    
    # Check Calibre is installed FIRST
    if not check_calibre_installed():
        raise FileNotFoundError(
            "Calibre (ebook-convert) is not installed. "
            "Please install Calibre: https://calibre-ebook.com/download"
        )
    
    # Validate input file exists
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Determine input format
    input_ext = Path(input_path).suffix.lower()
    if input_ext not in ['.docx', '.epub', '.pdf']:
        raise ValueError(f"Unsupported input format: {input_ext}")
    
    with TempDir(prefix="calibre_conv_") as temp_dir:
        try:
            htmlz_path = os.path.join(temp_dir, "output.htmlz")
            
            # Step 1: Convert to HTMLZ using Calibre
            # Note: ebook-convert determines format from file extensions
            logger.info(f"Converting {input_path} to HTMLZ...")
            cmd = [
                "ebook-convert",
                input_path,
                htmlz_path,
            ]
            
            calibre_timeout = int(getattr(config, 'calibre_timeout', 1800))
            try:
                _run_command(cmd, timeout=calibre_timeout)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if e.stderr else "Unknown error"
                stderr = stderr[:500]  # Limit for readability
                raise ValueError(f"Calibre conversion failed: {stderr}")
            except subprocess.TimeoutExpired:
                raise ValueError(f"Calibre conversion timed out (>{calibre_timeout}s)")

            if not os.path.exists(htmlz_path):
                raise ValueError("HTMLZ file was not created")
            
            # Step 2: Extract HTML from HTMLZ
            logger.info("Extracting HTML from HTMLZ...")
            html_content = ""
            metadata_opf = ""
            
            # Create images directory for HTMLZ images
            htmlz_images_dir = os.path.join(temp_dir, "htmlz_images")
            os.makedirs(htmlz_images_dir, exist_ok=True)
            
            with zipfile.ZipFile(htmlz_path, 'r') as zf:
                # Find and read the main HTML file
                for name in zf.namelist():
                    if name.endswith('.html') or name.endswith('.xhtml'):
                        html_content = zf.read(name).decode('utf-8')
                        break
                
                # Find and read metadata OPF
                for name in zf.namelist():
                    if name.endswith('.opf'):
                        metadata_opf = zf.read(name).decode('utf-8')
                        break
                
                # Extract images from HTMLZ
                image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')
                # C8 fix: keep images in a persistent dir next to the input file;
                # the temp dir is deleted when convert_to_markdown returns
                persistent_images_dir = os.path.splitext(input_path)[0] + '_images'
                try:
                    os.makedirs(persistent_images_dir, exist_ok=True)
                except OSError as e:
                    logger.warning(f"Cannot create persistent images dir {persistent_images_dir}: {e}")
                    persistent_images_dir = None
                for name in zf.namelist():
                    if name.lower().endswith(image_extensions):
                        try:
                            img_data = zf.read(name)
                            img_name = os.path.basename(name)
                            img_path = os.path.join(htmlz_images_dir, img_name)
                            with open(img_path, 'wb') as img_file:
                                img_file.write(img_data)
                            if persistent_images_dir:
                                persistent_img_path = os.path.join(persistent_images_dir, img_name)
                                with open(persistent_img_path, 'wb') as img_file:
                                    img_file.write(img_data)
                        except Exception as e:
                            logger.warning(f"Failed to extract image {name}: {e}")
            
            # Step 2b: Clean Calibre markers from HTML (before Markdown conversion)
            if html_content:
                logger.info("Cleaning Calibre markers from HTML...")
                html_content = _clean_calibre_markers(html_content)
            
            if not html_content:
                raise ValueError("No HTML content found in HTMLZ")
            
            # Step 3: Extract metadata from OPF
            metadata = {}
            if metadata_opf:
                metadata = extract_metadata_from_opf(metadata_opf)
            
            # Step 4: Convert HTML to Markdown using pypandoc
            logger.info("Converting HTML to Markdown...")
            if not PANDOC_AVAILABLE:
                raise FileNotFoundError(
                    "pypandoc is not installed. "
                    "Install it: pip install pypandoc (requires pandoc: https://pandoc.org/installing.html)"
                )
            # File-to-file via the real pandoc binary (not pypandoc.convert_text,
            # which offers no timeout) — mirrors the fix in _markdown_to_html_file
            # for the same reason: an in-memory, unbounded, timeout-less pandoc
            # call on a whole book can stall/OOM with no traceback.
            try:
                pandoc_exe = pypandoc.get_pandoc_path()
            except Exception:
                pandoc_exe = "pandoc"
            html_input_path = os.path.join(temp_dir, "input.html")
            with open(html_input_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            markdown_output_path = os.path.join(temp_dir, "output.md")
            pandoc_timeout = int(getattr(config, 'pandoc_timeout', 900))
            # Use --wrap=auto to prevent extremely long lines
            # This ensures better chunking behavior later
            cmd = [pandoc_exe, html_input_path, '-f', 'html', '-t', 'markdown',
                   '--wrap=auto', '-o', markdown_output_path]
            try:
                _run_command(cmd, timeout=pandoc_timeout)
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or "Unknown error")[:500]
                raise ValueError(f"Pandoc conversion failed: {stderr}")
            except subprocess.TimeoutExpired:
                raise ValueError(f"Pandoc conversion timed out (>{pandoc_timeout}s)")

            if not os.path.exists(markdown_output_path):
                raise ValueError("Pandoc did not produce Markdown output")

            with open(markdown_output_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read()
            # Remove surrogate code points produced by broken EPUB
            markdown_text = markdown_utils.sanitize_surrogates(markdown_text)
            
            # Step 5: Clean Calibre markers
            markdown_text = _clean_calibre_markers(markdown_text)
            # Second sanitize pass after marker cleaning
            markdown_text = markdown_utils.sanitize_surrogates(markdown_text)
            
            logger.info(f"Conversion complete: {len(markdown_text)} chars, title='{metadata.get('title', 'N/A')}'")
            
            return markdown_text, metadata
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise


def _clean_calibre_markers(text: str) -> str:
    """
    Remove Calibre-specific markers and clean up the text.
    
    Handles:
    - HTML Calibre markers: :::{#calibre_link-* .calibre*}:::
    - Inline Calibre markers: {#calibre_link-* .calibre*}
    - Class attributes: class="calibreX"
    
    Args:
        text: Markdown/HTML text with Calibre markers
        
    Returns:
        Cleaned text
    """
    if not text or not text.strip():
        return text
    
    # Remove Calibre comment markers like: <!-- 1 -->
    text = _RE_CALIBRE_COMMENT.sub('', text)
    
    # Remove Calibre section markers in HTML format (:::{...}::: inside <div> or <p>)
    text = _RE_CALIBRE_SECTION_FULL.sub('', text)
    text = _RE_CALIBRE_SECTION_CLASS.sub('', text)
    
    # Remove standalone :::
    text = _RE_CALIBRE_SECTION_BARE.sub('', text)
    text = _RE_CALIBRE_TRIPLE_COLON.sub('', text)
    
    # Remove HTML paragraphs containing only Calibre markers
    text = _RE_CALIBRE_PARA.sub('', text)
    
    # Remove inline Calibre markers (narrowed to Calibre-specific only)
    text = _RE_CALIBRE_ANCHOR.sub('', text)  # {#calibre_link-0 .calibre} and similar
    text = _RE_CALIBRE_CLASS.sub('', text)  # {.calibre1} and similar
    
    # Remove Calibre IDs: id="calibre_link-*"
    text = _RE_CALIBRE_ID_ATTR.sub('', text)
    
    # Remove Calibre class attributes from HTML tags
    text = _RE_CALIBRE_CLASS_ATTR.sub('', text)
    
    # Remove horizontal rules that are Calibre section markers
    text = _RE_HR_MARKERS.sub('\n\n', text)
    
    # Clean up multiple blank lines
    text = _RE_MULTI_BLANK.sub('\n\n', text)
    
    # Remove leading/trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


def _load_vocab_dict(book_path: str) -> dict:
    """
    Load vocabulary dictionary from .dic file.
    
    Parses the .dic file (format: source = target, category, gender, notes)
    and returns a simple source->target mapping.
    
    Args:
        book_path: Path to the book file (used to find corresponding .dic)
        
    Returns:
        Dictionary mapping source terms to target translations
    """
    from pathlib import Path
    
    book_dir = Path(book_path).parent
    book_name = Path(book_path).stem
    dic_path = book_dir / f"{book_name}.dic"
    
    if not dic_path.exists():
        return {}
    
    vocab = {}
    with open(dic_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            source, _, rest = line.partition('=')
            source = source.strip()
            rest = rest.strip()
            if not source or not rest:
                continue
            # Extract target (first field before comma)
            target = rest.split(',')[0].strip()
            if target:
                vocab[source] = target
    
    return vocab


def _load_vocab_entries(book_path: str) -> list:
    """
    Load vocabulary entries from .dic file as dict objects with full metadata.
    
    Parses the .dic file (format: source = target, category, gender, notes)
    and returns a list of dict objects with keys: source, target, category, gender, notes.
    
    Args:
        book_path: Path to the book file (used to find corresponding .dic)
        
    Returns:
        List of dict objects with vocabulary entry metadata
    """
    from pathlib import Path
    
    book_dir = Path(book_path).parent
    book_name = Path(book_path).stem
    dic_path = book_dir / f"{book_name}.dic"
    
    if not dic_path.exists():
        return []
    
    entries = []
    with open(dic_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            source, _, rest = line.partition('=')
            source = source.strip()
            rest = rest.strip()
            if not source or not rest:
                continue
            # Extract fields: target, category, gender, notes
            parts = rest.split(',')
            target = parts[0].strip() if parts else ""
            category = parts[1].strip() if len(parts) > 1 else ""
            gender = parts[2].strip() if len(parts) > 2 else ""
            notes = parts[3].strip() if len(parts) > 3 else ""
            
            entries.append({
                'source': source,
                'target': target,
                'category': category,
                'gender': gender,
                'notes': notes
            })
    
    return entries


def _protect_markdown_images(markdown_text: str) -> tuple[str, list[str]]:
    """Replace markdown image references with placeholder tokens before the
    text is sent to the translation LLM.

    Image markup (``![alt](images/foo.jpg)``) is not prose, and asking the
    LLM to translate a chunk containing it commonly drops or mangles the
    reference, silently losing the image from the final output. Swapping
    each occurrence for a short opaque token the LLM has no reason to touch
    keeps the reference intact through translation; _restore_markdown_images
    puts the original markup back afterwards.
    """
    images: list[str] = []

    def _replace(match: "re.Match[str]") -> str:
        images.append(match.group(0))
        return _IMG_PLACEHOLDER_FMT.format(len(images) - 1)

    protected = _RE_MD_IMAGE.sub(_replace, markdown_text)
    return protected, images


def _restore_markdown_images(text: str, images: list[str]) -> str:
    """Undo _protect_markdown_images after translation."""
    for idx, original in enumerate(images):
        text = text.replace(_IMG_PLACEHOLDER_FMT.format(idx), original)
    return text


def translate_chunks(
    markdown_text: str,
    max_chunk_size: int = 6000,
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    style: str = "text",
    fast_mode: bool = False,
    vocab_dict: Optional[dict] = None,
    book_path: Optional[str] = None,
    checkpoint_file: Optional[str] = None,
    remove_on_success: bool = True,
    stats_out: Optional['TranslationStats'] = None
) -> str:
    """
    Translate Markdown text in chunks using existing translate_chunk.

    This function:
    1. Splits text into chunks (respecting max_chunk_size)
    2. Translates each chunk using translate_chunk
    3. Reassembles the translated chunks
    4. Displays progress during translation

    Args:
        markdown_text: Markdown content to translate
        max_chunk_size: Maximum chunk size in characters (default 6000)
        source_lang: Source language code (default "en")
        target_lang: Target language code (default "ru")
        country: Target country for cultural context (default "Russia")
        style: Translation style - "text" or "xml" (default "text")
        fast_mode: Skip reflection/improve stages (default False)
        vocab_dict: Optional vocabulary dictionary. If None and book_path is provided,
                    will be loaded from book's .dic file
        book_path: Optional path to the book file (used to load vocabulary)
        checkpoint_file: Optional path to a checkpoint JSON for resume support
        remove_on_success: If True (default), delete the checkpoint once all
            chunks are translated. run_pipeline() passes False so the
            checkpoint survives a crash during build_output — it deletes the
            checkpoint itself only after the output file is built and
            validated, so a build failure doesn't discard the translation.
        stats_out: Optional TranslationStats instance to fill in-place with
            aggregate counters (source/target chars, chunk counts). Lets
            callers print a statistics report even though this function
            itself only returns the translated text.

    Returns:
        Translated markdown text
    """
    _init_logger()
    
    if not markdown_text or not markdown_text.strip():
        if logger:
            logger.warning("Empty markdown text, skipping translation")
        else:
            print("Empty markdown text, skipping translation")
        return markdown_text
    
    # Split into chunks using paragraph-aware splitter (for new Calibre pipeline)
    # This ensures chunks don't exceed max_chunk_size (unlike old _split_into_chunks)
    chunks = _split_into_chunks_md(markdown_text, max_chunk_size)
    total_chunks = len(chunks)
    
    if logger:
        logger.info(f"Text length: {len(markdown_text):,} chars, max_chunk_size: {max_chunk_size}")
        logger.info(f"Generated {total_chunks} chunks")
        
        # Log first few chunk sizes for debugging
        if len(chunks) > 0:
            sample_sizes = [len(c) for c in chunks[:5]]
            if len(chunks) > 5:
                sample_sizes.extend([len(c) for c in chunks[-2:]])
            logger.info(f"First chunk sizes: {sample_sizes}")
        
        logger.info(f"Translating {total_chunks} chunks (max_chunk_size={max_chunk_size})...")
    else:
        print(f"Text length: {len(markdown_text):,} chars, max_chunk_size: {max_chunk_size}")
        print(f"Generated {total_chunks} chunks")
        if len(chunks) > 0:
            sample_sizes = [len(c) for c in chunks[:5]]
            if len(chunks) > 5:
                sample_sizes.extend([len(c) for c in chunks[-2:]])
            print(f"First chunk sizes: {sample_sizes}")
        print(f"Translating {total_chunks} chunks (max_chunk_size={max_chunk_size})...")
    
    translated_parts = []
    outline_text = ""  # Context for next chunk
    vocab_entries = []  # Full metadata entries for 5-stage translation
    failed_chunks = 0  # Track chunks that failed translation

    # D5: checkpoint/resume support (per-chunk persistence)
    checkpoint_mgr = CheckpointManager(checkpoint_file) if checkpoint_file else None
    start_idx = 0
    start_time_iso = datetime.now().isoformat()
    total_source_len = 0
    total_target_len = 0
    if checkpoint_mgr is not None:
        saved = checkpoint_mgr.load()
        if saved is not None and os.path.realpath(saved.get("book_path", "")) == os.path.realpath(book_path or ""):
            start_idx = saved.get("last_chunk", -1) + 1
            extra = saved.get("extra", {}) or {}
            translated_parts = list(extra.get("translated_parts", []))
            outline_text = extra.get("outline_text", "")
            failed_chunks = int(extra.get("failed_chunks", 0))
            total_source_len = saved.get("lengths", {}).get("total_source_len", 0)
            total_target_len = saved.get("lengths", {}).get("total_target_len", 0)
            start_time_iso = saved.get("created_at", start_time_iso)
            logger.info(f"Resuming from checkpoint: chunk {start_idx}/{total_chunks}")
        elif saved is not None:
            logger.warning("Checkpoint belongs to another book, starting fresh")
            checkpoint_mgr.remove()

    # Load vocabulary if book_path provided and no explicit vocab_dict
    if vocab_dict is None and book_path:
        try:
            vocab_dict = _load_vocab_dict(book_path)
            if vocab_dict and logger:
                logger.info(f"Loaded vocabulary: {len(vocab_dict)} terms")
            # Also load vocab_entries for 5-stage translation
            vocab_entries = _load_vocab_entries(book_path)
            if vocab_entries and logger:
                logger.info(f"Loaded vocab_entries: {len(vocab_entries)} entries")
        except Exception as e:
            if logger:
                logger.warning(f"Failed to load vocabulary: {e}")
            else:
                print(f"Warning: Failed to load vocabulary: {e}")
            vocab_dict = {}
            vocab_entries = []
    elif vocab_dict is None:
        vocab_dict = {}
    
    for i, chunk in enumerate(chunks):
        if i < start_idx:
            continue  # already translated before the checkpoint

        # Sanitize surrogates before translation
        chunk = sanitize_surrogates(chunk)

        # Show progress
        progress = ((i + 1) / total_chunks) * 100
        print(f"\rProgress: {i + 1}/{total_chunks} ({progress:.1f}%)", end="", flush=True)
        
        # Translate chunk via utils.translate_chunk() (H2) — this routes through
        # the same _pipeline.execute but adds retry-on-empty, rechunking and the
        # MAX_LLM_CALLS_PER_CHUNK guard. The outer retry loop below additionally
        # catches exceptions that propagate out of translate_chunk.
        # M4: filter vocabulary to only terms appearing in current chunk
        chunk_vocab_dict = {}
        chunk_vocab_entries = []
        chunk_lower = chunk.lower()
        if vocab_dict:
            chunk_vocab_dict = {k: v for k, v in vocab_dict.items() if k.lower() in chunk_lower}
        if vocab_entries:
            chunk_vocab_entries = [e for e in vocab_entries if e.get('source', '').lower() in chunk_lower]
        translation = None
        for attempt in range(3):  # Up to 3 attempts
            try:
                translation, synopsis = translate_chunk(
                    source_lang=source_lang,
                    target_lang=target_lang,
                    source_text=chunk,
                    outline_text=outline_text,
                    vocab_dict=chunk_vocab_dict,
                    vocab_entries=chunk_vocab_entries,
                    country=country,
                    style=style,
                    fast_mode=fast_mode
                )
                
                outline_text = synopsis or ""
                break  # Success
                
            except Exception as e:
                logger.warning(f"Translation attempt {attempt + 1} failed for chunk {i + 1} ({type(e).__name__}): {e}")
                if attempt < 2:
                    backoff = 2 ** (attempt + 1)  # 2s, 4s
                    logger.info(f"Retrying chunk {i + 1} in {backoff}s...")
                    time.sleep(backoff)
        
        chunk_failed = False  # H3: failed chunks must not advance the checkpoint
        if translation is not None:
            # Validate translation length
            is_valid, percent_diff, should_split = validate_translation_length(
                chunk, translation, f"chunk_{i+1}"
            )
            
            if not is_valid:
                logger.warning(f"Chunk {i+1} length validation failed ({percent_diff:.1f}% diff)")
            
            # M7: warn when translation is abnormally large and should be rechunked
            if should_split:
                logger.warning(
                    f"Chunk {i+1} translation is {percent_diff:.1f}% larger than source "
                    f"— consider reducing --max-chunk-size for better quality"
                )
            
            # Fallback: if translation is empty, keep original
            if not translation or not translation.strip():
                print(f"Empty translation for chunk {i + 1}, keeping original")
                translation = chunk
                failed_chunks += 1
                chunk_failed = True
        else:
            # All retries exhausted
            logger.error(f"All retries exhausted for chunk {i + 1}, keeping original")
            translation = chunk
            failed_chunks += 1
            chunk_failed = True
        
        # Sanitize surrogates before storing
        translation = sanitize_surrogates(translation)
        translated_parts.append(translation)

        total_source_len += len(chunk)
        total_target_len += len(translation)

        # Save checkpoint after each chunk (D5)
        # M9/TODO: checkpoint saves the full translated_parts list each time,
        # leading to O(n²) I/O. For long books, consider append-only incremental
        # writes (e.g. one file per chunk + manifest) instead of full rewrite.
        # H3: failed chunks (empty translation or all retries exhausted) are written
        # to translated_parts as the original text so the current run can finish,
        # but they are NOT persisted to the checkpoint. Skipping the save keeps
        # last_chunk at the last successfully translated chunk, so a resumed run
        # starts at the failed chunk and retries it through the real LLM pipeline
        # instead of silently shipping the untranslated original text.
        if checkpoint_mgr is not None and not chunk_failed:
            checkpoint_mgr.save(
                chunk_id=i,
                section_idx=0,
                chunk_idx=i,
                stats={'successful': len(translated_parts) - failed_chunks,
                       'failed': failed_chunks},
                total_source_len=total_source_len,
                total_target_len=total_target_len,
                synopsis_history={},
                book_path=book_path or "",
                start_time_iso=start_time_iso,
                extra={
                    'translated_parts': translated_parts,
                    'outline_text': outline_text,
                    'failed_chunks': failed_chunks,
                },
            )
    
    print()  # New line after progress
    
    # Report failures
    if failed_chunks > 0:
        fail_pct = failed_chunks / total_chunks * 100
        logger.warning(f"⚠️ {failed_chunks}/{total_chunks} chunks failed to translate ({fail_pct:.1f}%)")
        # C11: by default ANY untranslated chunk is a failure; threshold is configurable
        max_failed_ratio = float(getattr(config, 'max_failed_chunk_ratio', 0.0))
        if failed_chunks / total_chunks > max_failed_ratio:
            raise RuntimeError(
                f"Translation failed: {failed_chunks}/{total_chunks} chunks ({fail_pct:.1f}%) untranslated. "
                f"Threshold: {max_failed_ratio:.0%}. Fix LLM output or raise max_failed_chunk_ratio."
            )
    
    # All chunks done: drop the checkpoint so the next run starts fresh,
    # unless the caller wants to keep it around until some later step (e.g.
    # run_pipeline keeps it until build_output/validate_output succeed, so a
    # crash during EPUB assembly doesn't throw away a finished translation).
    if checkpoint_mgr is not None and remove_on_success:
        checkpoint_mgr.remove()

    if stats_out is not None:
        stats_out.total_source_len = total_source_len
        stats_out.total_target_len = total_target_len
        stats_out.total_chunks = total_chunks
        stats_out.failed_chunks = failed_chunks

    # Reassemble translated text
    translated_text = '\n\n'.join(translated_parts)

    # Final sanitize pass before return
    translated_text = sanitize_surrogates(translated_text)

    if logger:
        logger.info(f"Translation complete: {len(translated_text)} chars")
    else:
        print(f"Translation complete: {len(translated_text)} chars")
    
    return translated_text


def _split_into_chunks_md(text: str, max_chunk_size: int) -> list[str]:
    """Split markdown into chunks, never breaking structural syntax.

    Uses structural-block-aware chunking (split_markdown_structured) so that
    fences, list markers, table rows and blockquote prefixes stay intact
    within a chunk — prevents LLM context fragmentation.
    """
    return markdown_utils.split_markdown_structured(text, target_size=max_chunk_size)


def _split_into_chunks(text: str, max_chunk_size: int) -> list[str]:
    """
    Split text into chunks of approximately max_chunk_size.
    
    Uses split_text_smartly for respecting paragraph boundaries.
    This is the ORIGINAL logic for backward compatibility with classic pipeline.
    
    Args:
        text: Text to split
        max_chunk_size: Maximum size per chunk
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    current_chunk = text
    
    while len(current_chunk) > max_chunk_size:
        # Try to split roughly in half
        first, rest = split_text_smartly(current_chunk)
        
        if not first:
            # Fallback: hard split at max_chunk_size
            first = current_chunk[:max_chunk_size]
            rest = current_chunk[max_chunk_size:]
        
        chunks.append(first)
        current_chunk = rest
    
    # Add remaining text
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def _markdown_to_html_file(
    markdown_text: str,
    html_path: str,
    temp_dir: str,
    batch_chars: int = 200000,
    timeout: int = 900,
) -> None:
    """Convert markdown to an HTML file on disk, batch by batch.

    This used to be a single pypandoc.convert_text() call on the whole
    book's markdown held as one Python string, with no timeout. On a
    ~920KB book that call stalled inside pandoc's own internals with no
    traceback: the log simply stopped after pypandoc's "Running pandoc..."
    debug line, and since nohup batched.sh runs books sequentially with
    `wait $app_pid`, the hang silently blocked every remaining book in the
    batch too.

    Splitting the markdown into batch_chars-sized batches (at structural
    block boundaries via markdown_utils.split_markdown_structured, so
    headings/tables/fences are never cut mid-block) and shelling out to the
    real `pandoc` binary file-to-file via _run_command bounds peak memory to
    one batch and gives every conversion call a real, enforced timeout —
    a stuck or oversized batch now raises ValueError instead of hanging.

    Raises:
        FileNotFoundError: pypandoc/pandoc is not installed.
        ValueError: a batch failed, timed out, or produced no output.
            Callers (build_output) are expected to catch this and fall back
            to feeding markdown directly to ebook-convert rather than leave
            a partially-written html_path in place.
    """
    if not PANDOC_AVAILABLE:
        raise FileNotFoundError(
            "pypandoc is not installed. "
            "Install it: pip install pypandoc (requires pandoc: https://pandoc.org/installing.html)"
        )

    try:
        pandoc_exe = pypandoc.get_pandoc_path()
    except Exception:
        pandoc_exe = "pandoc"

    if len(markdown_text) > batch_chars:
        batches = markdown_utils.split_markdown_structured(markdown_text, target_size=batch_chars)
    else:
        batches = [markdown_text]

    # Truncate/create html_path up front so callers see a real (if empty)
    # file rather than none at all if batches turns out to be empty.
    open(html_path, 'w', encoding='utf-8').close()

    for i, batch in enumerate(batches):
        batch_md_path = os.path.join(temp_dir, f"pandoc_batch_{i}.md")
        batch_html_path = os.path.join(temp_dir, f"pandoc_batch_{i}.html")
        with open(batch_md_path, 'w', encoding='utf-8') as f:
            f.write(batch)

        logger.info(
            f"Converting Markdown to HTML: batch {i + 1}/{len(batches)} "
            f"({len(batch):,} chars)..."
        )
        cmd = [pandoc_exe, batch_md_path, '-f', 'markdown', '-t', 'html', '--wrap=none', '-o', batch_html_path]
        try:
            _run_command(cmd, timeout=timeout)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "Unknown error")[:500]
            raise ValueError(f"Pandoc HTML conversion failed on batch {i + 1}/{len(batches)}: {stderr}")
        except subprocess.TimeoutExpired:
            raise ValueError(
                f"Pandoc HTML conversion timed out on batch {i + 1}/{len(batches)} "
                f"(>{timeout}s, {len(batch):,} chars). "
                f"Increase PANDOC_TIMEOUT or lower PANDOC_BATCH_CHARS."
            )

        if not os.path.exists(batch_html_path):
            raise ValueError(f"Pandoc did not produce output for batch {i + 1}/{len(batches)}")

        with open(batch_html_path, 'r', encoding='utf-8') as f:
            batch_html = f.read()

        # Same mutations the old single-shot conversion applied to the whole
        # document, now applied per batch, so html_path only ever accumulates
        # post-mutation content (mirrors the write-after-mutation invariant
        # the original code relied on).
        batch_html = markdown_utils.sanitize_surrogates(batch_html)
        batch_html = _clean_calibre_markers(batch_html)
        batch_html = markdown_utils.sanitize_surrogates(batch_html)
        batch_html = _RE_IMG_SRC.sub(r'\1\2\3', batch_html)

        with open(html_path, 'a', encoding='utf-8') as f:
            f.write(batch_html)
            f.write('\n')


def build_output(
    translated_md: str,
    output_format: str,
    metadata: dict,
    output_path: Optional[str] = None,
    images_dir: Optional[str] = None,
    input_path: Optional[str] = None,
    target_lang: Optional[str] = None
) -> str:
    """
    Build final output (FB2/EPUB) from translated Markdown.

    This function:
    1. Converts Markdown to HTML (with TOC) using pandoc
    2. Converts HTML to desired output format using Calibre
    3. Cleans up temporary files

    Args:
        translated_md: Translated Markdown content
        output_format: Output format - "docx", "epub" or "pdf"
        metadata: Book metadata dictionary
        output_path: Optional output path (auto-generated if not provided)
        input_path: Source file path. When output_path is not given, the
            output is placed next to this file instead of the CWD.
        target_lang: Target language, used to append a language marker
            (e.g. "_ru") to the auto-generated filename. Falls back to
            config.target_lang when not given.

    Returns:
        Path to the generated output file

    Raises:
        ValueError: If output format is invalid
        FileNotFoundError: If Calibre is not installed
    """
    _init_logger()
    
    # Validate translated markdown is not empty or identical to source
    if not translated_md or not translated_md.strip():
        raise ValueError("Translated markdown is empty or whitespace")
    
    # Check if markdown looks like it hasn't been translated (still mostly English)
    # Simple heuristic: if more than 85% of letters are ASCII (Latin), the text
    # likely wasn't translated into Cyrillic/other non-Latin target languages.
    # NOTE: compare ASCII letters against total Latin+Cyrillic letters only,
    # so punctuation/digits/markup don't skew the ratio.
    import re
    ascii_letters = len(re.findall(r'[a-zA-Z]', translated_md))
    cyrillic_letters = len(re.findall(r'[\u0400-\u04FF]', translated_md))
    total_letters = ascii_letters + cyrillic_letters
    ascii_ratio = ascii_letters / total_letters if total_letters > 0 else 0
    
    if ascii_ratio > 0.85 and config.target_lang.lower() != 'english':
        logger.warning(f"High ASCII ratio ({ascii_ratio:.1%}) in translated markdown. "
                      f"May indicate translation failed or output not replaced properly.")
    
    output_format = output_format.lower()
    valid_formats = {'docx', 'epub', 'pdf'}
    if output_format not in valid_formats:
        raise ValueError(f"Unsupported output format: {output_format}. Valid: {', '.join(sorted(valid_formats))}")
    
    # Check Calibre is installed
    if not check_calibre_installed():
        raise FileNotFoundError(
            "Calibre (ebook-convert) is not installed. "
            "Please install Calibre: https://calibre-ebook.com/download"
    )
    
    # Generate output filename if not provided
    if not output_path:
        title = metadata.get('title', 'output')
        # Sanitize filename: remove special chars and spaces
        safe_title = re.sub(r'[^\w\-]', '_', title).strip()[:50]
        # Language marker (e.g. "_ru") so translations of the same book
        # into different languages don't overwrite each other.
        lang = (target_lang or config.target_lang or '').lower()
        lang_marker = config.lang_code_map.get(lang, lang)
        # Save next to the source file instead of the CWD.
        out_dir = os.path.dirname(input_path) if input_path else ''
        out_dir = out_dir or '.'
        filename = f"{safe_title}_{lang_marker}.{output_format}" if lang_marker else f"{safe_title}.{output_format}"
        output_path = os.path.join(out_dir, filename)
    
    with TempDir(prefix="calibre_output_") as temp_dir:
        try:
            # C8 fix: put book images next to the temp dir so ebook-convert
            # embeds them, whichever conversion path below is taken. Mirrored
            # under images/ too (not just the root) so the markdown-fallback
            # path — which still references "images/foo.jpg" verbatim,
            # unlike the HTML path where _RE_IMG_SRC strips the prefix below
            # — resolves without needing a second rewrite regex.
            if images_dir and os.path.isdir(images_dir):
                import shutil
                images_subdir = os.path.join(temp_dir, "images")
                os.makedirs(images_subdir, exist_ok=True)
                for img_name in os.listdir(images_dir):
                    src_img = os.path.join(images_dir, img_name)
                    if os.path.isfile(src_img):
                        shutil.copy2(src_img, os.path.join(temp_dir, img_name))
                        shutil.copy2(src_img, os.path.join(images_subdir, img_name))

            # Add metadata as title page
            title_html = _generate_title_page(metadata)
            full_markdown = f"{title_html}\n\n{translated_md}"

            # Step 1: Convert Markdown to HTML (batched, file-to-file, with a
            # real timeout — see _markdown_to_html_file for why the old
            # single-shot pypandoc.convert_text() call was replaced).
            html_path = os.path.join(temp_dir, "output.html")
            conversion_input_path = html_path
            using_markdown_fallback = False

            try:
                logger.info("Converting Markdown to HTML...")
                _markdown_to_html_file(
                    full_markdown,
                    html_path,
                    temp_dir=temp_dir,
                    batch_chars=int(getattr(config, 'pandoc_batch_chars', 200000)),
                    timeout=int(getattr(config, 'pandoc_timeout', 900)),
                )
            except Exception as e:
                # pandoc missing, or every batch failed/timed out: Calibre
                # understands markdown input natively, so feed it the raw
                # markdown instead of failing the whole build over a pandoc
                # hiccup. Formatting/TOC may differ slightly from the
                # pandoc-HTML path — this is a safety net, not the norm.
                logger.warning(
                    f"Markdown→HTML conversion via pandoc failed ({e}); "
                    f"falling back to feeding markdown directly to Calibre. "
                    f"Output formatting/TOC may differ."
                )
                md_fallback_path = os.path.join(temp_dir, "book.md")
                with open(md_fallback_path, 'w', encoding='utf-8') as f:
                    f.write(full_markdown)
                conversion_input_path = md_fallback_path
                using_markdown_fallback = True

            # Step 3: Convert HTML (or markdown fallback) to output format using Calibre
            logger.info(
                f"Converting {'Markdown' if using_markdown_fallback else 'HTML'} "
                f"to {output_format.upper()}..."
            )
            cmd = [
                "ebook-convert",
                conversion_input_path,
                output_path,
            ]
            # C9 fix: pass metadata to Calibre so it lands in the output file
            if metadata.get('title'):
                cmd += ["--title", str(metadata['title'])]
            if metadata.get('author'):
                cmd += ["--authors", str(metadata['author'])]
            if metadata.get('language'):
                cmd += ["--language", str(metadata['language'])]

            calibre_timeout = int(getattr(config, 'calibre_timeout', 1800))
            try:
                _run_command(cmd, timeout=calibre_timeout)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if e.stderr else "Unknown error"
                stderr = stderr[:500]  # Limit for readability
                raise ValueError(f"Calibre output conversion failed: {stderr}")
            except subprocess.TimeoutExpired:
                raise ValueError(f"Calibre output conversion timed out (>{calibre_timeout}s)")

            if not os.path.exists(output_path):
                raise ValueError(f"Output file was not created: {output_path}")

            logger.info(f"Output created: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Output build failed: {e}")
            raise


def _generate_title_page(metadata: dict) -> str:
    """
    Generate HTML title page from metadata.
    
    Args:
        metadata: Book metadata dictionary
        
    Returns:
        HTML string for title page
    """
    import html as _html
    # C2 fix: escape all metadata values to prevent HTML injection
    _e = lambda s: _html.escape(str(s), quote=True)
    title = _e(metadata.get('title', 'Untitled'))
    author = _e(metadata.get('author', ''))
    publisher = _e(metadata.get('publisher', ''))
    language = _e(metadata.get('language', ''))
    description = _e(metadata.get('description', ''))
    
    # C9 fix: title page must be an HTML fragment, not a full document
    html = f"""<div class="titlepage">
<h1>{title}</h1>
"""
    
    if author:
        html += f"<h2>by {author}</h2>\n"
    
    if publisher:
        html += f"<p><em>{publisher}</em></p>\n"
    
    if language:
        html += f"<p>Language: {language}</p>\n"
    
    if description:
        html += f"<p>{description}</p>\n"
    
    html += "</div>"
    
    return html


def _add_toc_to_html(markdown_text: str) -> str:
    """Add TOC to HTML after pandoc conversion."""
    from bs4 import BeautifulSoup
    
    if not PANDOC_AVAILABLE:
        raise ImportError("pypandoc is required for TOC generation")
    
    html_content = pypandoc.convert_text(markdown_text, 'html', format='markdown')
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = markdown_utils.extract_headings(soup)
    toc_html = markdown_utils.generate_toc_html(headings)
    
    if soup.body:
        soup.body.insert(0, BeautifulSoup(toc_html, 'html.parser').nav)
    elif soup.html:
        soup.html.insert(0, BeautifulSoup(toc_html, 'html.parser').nav)
    
    return str(soup)


# ---------------------------------------------------------------------------
# Output file validation
# ---------------------------------------------------------------------------

def validate_epub(output_path: str) -> ValidationReport:
    """
    Validate EPUB file structure and content.

    Checks:
    - File exists and size > 0
    - Valid ZIP structure
    - META-INF/container.xml exists
    - OPF file exists and contains dc:title / dc:creator
    - TOC file present (warning if missing)
    - No Calibre artifact markers

    Args:
        output_path: Path to EPUB file

    Returns:
        ValidationReport with results
    """
    _init_logger()
    report = ValidationReport(is_valid=False, file_path=output_path, format="epub")

    # --- File existence & size ---
    if not os.path.exists(output_path):
        report.add_issue("error", "File does not exist")
        return report

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        report.add_issue("error", "File is empty")
        return report
    report.file_size = file_size

    # --- ZIP structure ---
    try:
        with zipfile.ZipFile(output_path, 'r') as zf:
            names = set(zf.namelist())

            # container.xml
            if 'META-INF/container.xml' not in names:
                report.add_issue("error", "Missing META-INF/container.xml")

            # OPF file
            opf_files = [n for n in names if n.endswith('.opf')]
            if not opf_files:
                report.add_issue("error", "No OPF file found in EPUB")
            else:
                for opf_name in opf_files:
                    with zf.open(opf_name) as f:
                        opf_content = f.read().decode('utf-8', errors='replace')
                    if '<dc:title>' not in opf_content:
                        report.add_issue("error", f"Missing <dc:title> in {opf_name}")
                    # M3: use regex (same as metadata extraction) to match dc:creator with attributes
                    if not re.search(r'<dc:creator[^>]*>', opf_content, re.IGNORECASE):
                        report.add_issue("warning", f"Missing <dc:creator> in {opf_name}")

            # TOC (NCX or NAV / XHTML with 'toc' in name)
            toc_found = (
                any('toc' in n.lower() for n in names)
                or any(n.endswith('.ncx') for n in names)
            )
            if not toc_found:
                report.add_issue("warning", "No TOC file found")

            # Calibre artifacts
            for name in names:
                if 'calibre' in name.lower():
                    report.add_issue("warning", f"Calibre artifact found: {name}")

    except zipfile.BadZipFile:
        report.add_issue("error", "Invalid ZIP structure (not a valid EPUB)")
        return report

    report.is_valid = not report.has_errors()
    logger.info(f"EPUB validation: {report.summary()}")
    return report


def validate_fb2(output_path: str) -> ValidationReport:
    """
    Validate FB2 file structure and content.

    Checks:
    - File exists and size > 0
    - Valid XML structure
    - Root element is FictionBook (with FB2 namespace)
    - <title-info> section present
    - <body> section present
    - No Calibre artifact markers

    Args:
        output_path: Path to FB2 file

    Returns:
        ValidationReport with results
    """
    _init_logger()
    report = ValidationReport(is_valid=False, file_path=output_path, format="fb2")

    if not os.path.exists(output_path):
        report.add_issue("error", "File does not exist")
        return report

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        report.add_issue("error", "File is empty")
        return report
    report.file_size = file_size

    # --- XML parsing ---
    try:
        tree = ET.parse(output_path)
        root = tree.getroot()
    except ET.ParseError as e:
        report.add_issue("error", f"Invalid XML structure: {e}")
        return report

    # FB2 namespace
    FB2_NS = 'http://www.gribuser.ru/xml/fictionbook/2.0'
    ns = {'fb2': FB2_NS}

    # Root element check — accept with or without namespace
    root_tag = root.tag
    if root_tag != f'{{{FB2_NS}}}FictionBook' and root_tag != 'FictionBook':
        report.add_issue("error", f"Invalid FB2 root element: {root_tag}")
        return report

    # title-info
    title_info = root.find('.//fb2:title-info', ns)
    if title_info is None:
        # Try without namespace
        title_info = root.find('.//title-info')
    if title_info is None:
        report.add_issue("error", "Missing <title-info> section")

    # body
    bodies = root.findall('.//fb2:body', ns)
    if not bodies:
        bodies = root.findall('.//body')
    if not bodies:
        report.add_issue("error", "Missing <body> section")

    # Calibre artifacts
    with open(output_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if 'calibre-' in content.lower():
        report.add_issue("warning", "Calibre artifact found in FB2 content")

    report.is_valid = not report.has_errors()
    logger.info(f"FB2 validation: {report.summary()}")
    return report


def validate_docx(output_path: str) -> ValidationReport:
    """
    Validate DOCX file structure and content.

    Checks:
    - File exists and size > 0
    - Valid ZIP (OOXML) structure
    - word/document.xml present
    - [Content_Types].xml present

    Args:
        output_path: Path to DOCX file

    Returns:
        ValidationReport with results
    """
    _init_logger()
    report = ValidationReport(is_valid=False, file_path=output_path, format="docx")

    if not os.path.exists(output_path):
        report.add_issue("error", "File does not exist")
        return report

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        report.add_issue("error", "File is empty")
        return report
    report.file_size = file_size

    try:
        with zipfile.ZipFile(output_path, 'r') as zf:
            names = set(zf.namelist())
            if 'word/document.xml' not in names:
                report.add_issue("error", "Missing word/document.xml")
            if '[Content_Types].xml' not in names:
                report.add_issue("error", "Missing [Content_Types].xml")
            # Ensure document.xml parses as XML
            if 'word/document.xml' in names:
                try:
                    zf.read('word/document.xml')
                except Exception as e:
                    report.add_issue("error", f"Cannot read word/document.xml: {e}")
    except zipfile.BadZipFile:
        report.add_issue("error", "Invalid ZIP structure (not a valid DOCX)")
        return report

    report.is_valid = not report.has_errors()
    logger.info(f"DOCX validation: {report.summary()}")
    return report


def validate_pdf(output_path: str) -> ValidationReport:
    """
    Validate PDF file structure and content.

    Checks:
    - File exists and size > 0
    - Starts with %PDF-
    - Contains EOF marker (%%EOF)

    Args:
        output_path: Path to PDF file

    Returns:
        ValidationReport with results
    """
    _init_logger()
    report = ValidationReport(is_valid=False, file_path=output_path, format="pdf")

    if not os.path.exists(output_path):
        report.add_issue("error", "File does not exist")
        return report

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        report.add_issue("error", "File is empty")
        return report
    report.file_size = file_size

    with open(output_path, 'rb') as f:
        header = f.read(1024)
    if not header.startswith(b'%PDF-'):
        report.add_issue("error", "Invalid PDF header (missing %PDF-)")

    with open(output_path, 'rb') as f:
        # Read trailing bytes (handle files smaller than 1024 bytes)
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 1024), 0)
        tail = f.read()
    if b'%%EOF' not in tail:
        report.add_issue("warning", "Missing %%EOF marker")

    report.is_valid = not report.has_errors()
    logger.info(f"PDF validation: {report.summary()}")
    return report


def validate_output(output_path: str, output_format: str) -> ValidationReport:
    """
    Validate output file based on format.

    Dispatches to validate_epub() or validate_fb2() depending on format.

    Args:
        output_path: Path to output file
        output_format: "docx", "epub" or "pdf"

    Returns:
        ValidationReport with results
    """
    _init_logger()
    fmt = output_format.lower()
    if fmt == "epub":
        return validate_epub(output_path)
    elif fmt == "docx":
        return validate_docx(output_path)
    elif fmt == "pdf":
        return validate_pdf(output_path)
    elif fmt == "fb2":
        report = ValidationReport(is_valid=False, file_path=output_path, format=fmt)
        report.add_issue(
            "error",
            f"FB2 output is not supported by the Calibre pipeline. "
            f"Use the classic pipeline for FB2.",
        )
        return report
    else:
        report = ValidationReport(is_valid=False, file_path=output_path, format=fmt)
        report.add_issue("error", f"Unsupported output format: {output_format}")
        return report


# --- Dictionary Builder ---

def extract_dictionary_from_md(
    source_md: str,
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    min_count_ner: int = 5,
    min_count_word: int = 10,
    min_word_length: int = 5
) -> List[Dict]:
    """
    Extract dictionary entries from source markdown using NER.

    Algorithm:
    1. Use NER (spaCy) to identify named entities (PERSON, LOC, ORG)
    2. Extract frequent words (filtered by min_count_word, min_word_length)
    3. Translate extracted terms via LLM (utils.vocabulary)
    4. Parse LLM response into structured dictionary entries

    Args:
        source_md: Source (untranslated) markdown text
        source_lang: Source language code (default "en")
        target_lang: Target language code (default "ru")
        country: Target country for cultural context (default "Russia")
        min_count_ner: Minimum occurrences for NER entities (default 5)
        min_count_word: Minimum occurrences for common words (default 10)
        min_word_length: Minimum word length for common words (default 5)

    Returns:
        List of dictionary entries: [{'source': ..., 'target': ..., 'category': ..., 'gender': '', 'notes': ...}, ...]
    """
    _init_logger()

    if not source_md or not source_md.strip():
        logger.warning("extract_dictionary_from_md: empty source text")
        return []

    # Step 1: Extract terms using NER (reuses existing ner.create_dictionary_from_text)
    from src import ner as ner_module

    logger.info(
        f"Extracting dictionary terms via NER "
        f"(min_count_ner={min_count_ner}, min_count_word={min_count_word}, "
        f"min_word_length={min_word_length})..."
    )

    extracted_terms = ner_module.create_dictionary_from_text(
        source_md,
        min_count_ner=min_count_ner,
        min_count_word=min_count_word,
        min_word_length=min_word_length
    )

    if not extracted_terms:
        logger.info("No terms extracted by NER")
        return []

    logger.info(f"Extracted {len(extracted_terms)} terms from source text")

    # Step 2: Format terms for LLM translation
    terms_text = '\n'.join([term for term, cat, notes in extracted_terms])

    # Split into chunks for LLM (respect max_len_chunk)
    chunk_size = int(config.max_len_chunk) if hasattr(config, 'max_len_chunk') else 16384
    lines = terms_text.split('\n')
    chunks = []
    current: list = []
    current_len = 0
    for line in lines:
        current.append(line)
        current_len += len(line) + 1
        if current_len >= chunk_size:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0
    if current:
        chunks.append('\n'.join(current))

    logger.info(f"Split {len(terms_text)} chars into {len(chunks)} chunk(s) for translation")

    # Step 3: Translate each chunk via LLM
    from src import utils as ta

    all_translations: Dict[str, str] = {}  # source_lower -> target

    for idx, chunk in enumerate(chunks):
        logger.info(f"Translating dictionary chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")
        try:
            vocab_translated = ta.vocabulary(
                source_lang, target_lang, chunk, country, "translate"
            )
            # Parse translations from LLM response
            chunk_translations = _parse_dictionary_llm_response(vocab_translated)
            all_translations.update(chunk_translations)
            logger.info(f"  Chunk {idx + 1}: parsed {len(chunk_translations)} translations")
        except Exception as e:
            logger.error(f"  Chunk {idx + 1} translation failed: {e}")

    # Step 4: Build structured dictionary entries
    dictionary: List[Dict] = []
    valid_categories = {'PERSON', 'LOC', 'ORG', 'GPE', 'TERM'}

    for term, category, notes in extracted_terms:
        term_lower = term.lower()
        target = all_translations.get(term_lower, "")

        if not target:
            # Try case-insensitive lookup
            for src_key, tgt_val in all_translations.items():
                if src_key == term_lower:
                    target = tgt_val
                    break

        if not target:
            logger.debug(f"No translation found for term '{term}', skipping")
            continue

        # Normalize category
        if category.upper() not in valid_categories:
            category = "TERM"
        else:
            category = category.upper()

        dictionary.append({
            'source': term,
            'target': target,
            'category': category,
            'gender': '',
            'notes': notes or 'auto-extracted from source markdown'
        })

    logger.info(f"Dictionary built: {len(dictionary)} entries (from {len(extracted_terms)} extracted terms)")
    return dictionary


def _parse_dictionary_llm_response(vocab_translated: str) -> Dict[str, str]:
    """
    Parse LLM vocabulary response into source->target mapping.

    Handles multiple response formats:
    - JSON array: [{"source": "...", "target": "..."}, ...]
    - Markdown table: | source | target | category |
    - Key-value: source = target / source: target / source → target

    Args:
        vocab_translated: Raw LLM response text

    Returns:
        Dict mapping source_lower -> target
    """
    import json as _json

    translations: Dict[str, str] = {}
    if not vocab_translated or not vocab_translated.strip():
        return translations

    # Strategy 1: JSON array
    try:
        json_array_match = re.search(r'\[\s*\{.*?\}\s*\]', vocab_translated, re.DOTALL)
        if json_array_match:
            terms = _json.loads(json_array_match.group(0))
            if isinstance(terms, list):
                for item in terms:
                    if isinstance(item, dict):
                        src = str(item.get('source', '')).strip()
                        tgt = str(item.get('target', '')).strip()
                        if src and tgt:
                            translations[src.lower()] = tgt
                if translations:
                    return translations
    except (_json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Markdown table
    table_pattern = r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'
    matches = re.findall(table_pattern, vocab_translated)
    if matches:
        for match in matches:
            source = match[0].strip()
            target = match[1].strip()
            if (source and target
                    and not source.startswith('-')
                    and not target.startswith('-')
                    and source.lower() not in ('source', 'term', 'english')):
                translations[source.lower()] = target
        if translations:
            return translations

    # Strategy 3: Key-value patterns
    kv_patterns = [
        r'"([^"]+)"\s*:\s*"([^"]+)"',   # "source": "target"
        r'([^:=\n]+)[=:]\s*([^\n]+)',      # source = target / source: target
        r'([^→\n]+)→\s*([^\n]+)',          # source → target
    ]
    for pattern in kv_patterns:
        matches = re.findall(pattern, vocab_translated)
        if matches:
            for match in matches:
                source = match[0].strip()
                target = match[1].strip()
                if (source and target
                        and len(source) > 1
                        and len(target) > 1
                        and source.lower() not in ('source', 'terms', 'translation', 'note')):
                    translations[source.lower()] = target
            if translations:
                return translations

    return translations


def save_dictionary(dictionary: List[Dict], output_path: str) -> None:
    """
    Save dictionary entries in .dic format.

    Format (compatible with _load_vocab_dict / _load_vocab_entries):
        # Vocabulary header
        source = target, category, gender, notes

    Args:
        dictionary: List of dictionary entries from extract_dictionary_from_md()
        output_path: Output .dic file path
    """
    _init_logger()

    if not dictionary:
        logger.warning("save_dictionary: empty dictionary, nothing to save")
        return

    # Ensure parent directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Vocabulary dictionary\n")
        f.write(f"# Format: source = target, category, gender, notes\n")
        f.write(f"# Generated automatically from source markdown by NER + LLM\n")
        f.write(f"# Entries: {len(dictionary)}\n\n")

        for entry in dictionary:
            source = entry.get('source', '')
            target = entry.get('target', '')
            category = entry.get('category', '')
            gender = entry.get('gender', '')
            notes = entry.get('notes', '')

            if not source or not target:
                continue

            line = f"{source} = {target}"
            if category:
                line += f", {category}"
            if gender:
                line += f", {gender}"
            if notes:
                line += f", {notes}"
            f.write(line + '\n')

    logger.info(f"Dictionary saved: {output_path} ({len(dictionary)} entries)")


def _enforce_validation(validation, allow_invalid: bool) -> None:
    """C10: raise when validation found errors unless explicitly allowed."""
    if validation.is_valid or allow_invalid:
        return
    raise RuntimeError(
        f"Output validation failed ({validation.file_path}): {validation.summary()}"
    )


def _atomic_write_text(path: str, content: str) -> None:
    """Write text to `path` atomically (temp file + os.replace).

    Same pattern as CheckpointManager.save() — a crash mid-write leaves the
    original file (or nothing) rather than a half-written one.
    """
    tmp_path = path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp_path, path)


def _dump_translation(
    translated_dump_path: str,
    meta_dump_path: str,
    translated_md: str,
    metadata: dict,
    stats: 'TranslationStats',
) -> None:
    """Persist a finished translation to disk before build_output runs.

    Without this, a crash/hang during build_output (pandoc/ebook-convert)
    throws away the entire translation — nothing in the Calibre pipeline
    wrote the translated Markdown anywhere, only a temporary output.html
    inside a TempDir that gets rmtree'd. run_pipeline reads these files back
    on the next run (see its resume logic) and skips straight to Step 4,
    so a build failure costs zero additional LLM calls to recover from.
    """
    _atomic_write_text(translated_dump_path, translated_md)
    payload = {
        'metadata': metadata,
        'translation_stats': {
            'total_source_len': stats.total_source_len,
            'total_target_len': stats.total_target_len,
            'total_chunks': stats.total_chunks,
            'failed_chunks': stats.failed_chunks,
        },
    }
    _atomic_write_text(meta_dump_path, json.dumps(payload, ensure_ascii=False, indent=2))


# Convenience function for full pipeline
def run_pipeline(
    input_path: str,
    output_format: str = "epub",
    max_chunk_size: int = None,  # None = use MAX_LEN_CHUNK from config
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    fast_mode: bool = False,
    skip_validation: bool = False,
    allow_invalid: bool = False,
    checkpoint_file: Optional[str] = None,
    fresh: bool = False,
    stats_out: Optional['TranslationStats'] = None
) -> str:
    """
    Run the complete Calibre pipeline: convert -> translate -> build output -> validate.

    Args:
        input_path: Path to input DOCX/EPUB/PDF file
        output_format: Output format - "docx", "epub" or "pdf"
        max_chunk_size: Maximum chunk size for translation
        source_lang: Source language code
        target_lang: Target language code
        country: Target country for cultural context
        fast_mode: Skip reflection/improve stages
        skip_validation: Skip output validation step (for testing)
        checkpoint_file: Optional path to a translation checkpoint JSON. If
            not given, one is derived from input_path + target_lang next to
            the source file (deterministic, no timestamp — same naming
            convention as app.py:build_resume_paths for the classic
            pipeline; see CLAUDE.md's output-file-naming section).
        fresh: If True, ignore any existing checkpoint and translated-Markdown
            dump and translate the book from scratch.
        stats_out: Optional TranslationStats instance filled in-place with
            aggregate counters (source/target chars, chunk counts), so
            callers can print the same statistics report the classic FB2
            pipeline prints via src.utils.print_translation_report().

    Returns:
        Path to the generated output file
    """
    _init_logger()

    # Validate input/output format scope: Calibre pipeline is for
    # DOCX/EPUB/PDF only. FB2 stays with the classic pipeline (direct XML
    # manipulation) because Calibre's HTMLZ intermediate loses FB2 structure
    # (poem/stanza/v etc.) and flattens it into <p>/<empty-line/>.
    from pathlib import Path as _Path
    input_ext = _Path(input_path).suffix.lower()
    if input_ext not in ('.docx', '.epub', '.pdf'):
        raise ValueError(
            f"Unsupported input format for Calibre pipeline: {input_ext}. "
            f"Calibre pipeline supports DOCX/EPUB/PDF. "
            f"For FB2 use the classic pipeline (without --pipeline new)."
        )
    output_format = (output_format or 'epub').lower()
    if output_format not in ('docx', 'epub', 'pdf'):
        raise ValueError(
            f"Unsupported output format for Calibre pipeline: {output_format}. "
            f"Valid: docx, epub, pdf. For FB2 use the classic pipeline."
        )

    # Deterministic (no timestamp) paths next to the source file, so a
    # second run on the same book finds what the first run left behind.
    stem = os.path.splitext(input_path)[0]
    lang_marker = config.lang_code_map.get((target_lang or '').lower(), (target_lang or '').lower())
    suffix = f"_{lang_marker}" if lang_marker else ""
    if checkpoint_file is None:
        checkpoint_file = f"{stem}{suffix}.checkpoint.json"
    translated_dump_path = f"{stem}{suffix}.translated.md"
    meta_dump_path = f"{stem}{suffix}.meta.json"

    # Resume fast path: a previous run that got all the way through
    # translation but crashed/hung during build_output (pandoc/ebook-convert
    # — see _markdown_to_html_file's docstring for the incident this
    # closes) left the finished translation on disk. Reuse it instead of
    # re-translating the whole book through the LLM again.
    translated_md = None
    metadata = None
    if not fresh and os.path.exists(translated_dump_path) and os.path.exists(meta_dump_path):
        try:
            if os.path.getmtime(translated_dump_path) >= os.path.getmtime(input_path):
                with open(translated_dump_path, 'r', encoding='utf-8') as f:
                    translated_md = f.read()
                with open(meta_dump_path, 'r', encoding='utf-8') as f:
                    dump_payload = json.load(f)
                metadata = dump_payload.get('metadata', {}) or {}
                dumped_stats = dump_payload.get('translation_stats') or {}
                if stats_out is not None:
                    stats_out.total_source_len = dumped_stats.get('total_source_len', 0)
                    stats_out.total_target_len = dumped_stats.get('total_target_len', 0)
                    stats_out.total_chunks = dumped_stats.get('total_chunks', 0)
                    stats_out.failed_chunks = dumped_stats.get('failed_chunks', 0)
                logger.info(
                    f"Steps 1-3 skipped: reusing translated Markdown from "
                    f"{translated_dump_path} (newer than {input_path}). "
                    f"Pass fresh=True (--fresh) to force a full re-translation."
                )
            else:
                logger.info(
                    f"Translated dump {translated_dump_path} is older than "
                    f"{input_path}; translating from scratch."
                )
        except Exception as e:
            logger.warning(f"Failed to reuse translated dump ({e}); translating from scratch")
            translated_md = None
            metadata = None

    # C8: convert_to_markdown persists images next to the input file — true
    # whether or not Steps 1-3 run on this call.
    images_dir = os.path.splitext(input_path)[0] + '_images'

    if translated_md is None:
        # Step 1: Convert to Markdown
        logger.info(f"Step 1/5: Converting {input_path} to Markdown...")
        markdown_text, metadata = convert_to_markdown(input_path)

        # Step 2: Build dictionary if .dic doesn't exist (M6: build BEFORE translation
        # so the first run has vocabulary terms available)
        dic_path = Path(input_path).with_suffix('.dic')
        if not dic_path.exists():
            logger.info("Step 2/5: Building dictionary from source markdown...")
            try:
                dictionary = extract_dictionary_from_md(
                    markdown_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    country=country
                )
                if dictionary:
                    save_dictionary(dictionary, str(dic_path))
                    logger.info(f"  Dictionary created: {dic_path} ({len(dictionary)} entries)")
                else:
                    logger.info("  No dictionary terms extracted")
            except Exception as e:
                logger.warning(f"  Dictionary building failed (non-fatal): {e}")
        else:
            logger.info(f"Step 2/5: Dictionary already exists: {dic_path} (skipped)")

        # Step 3: Translate
        logger.info("Step 3/5: Translating...")

        # Use MAX_LEN_CHUNK from config if max_chunk_size not specified.
        # NOTE: local var is named `cfg`, not `config` — assigning to
        # `config` here would make it a function-local name for the *whole*
        # function (Python scoping), shadowing the module-level `config`
        # used above (lang_code_map) and below (build_output/translate_chunks
        # indirectly), which would raise UnboundLocalError.
        if max_chunk_size is None:
            try:
                from src.config import Config
                cfg = Config()
                max_chunk_size = cfg.max_len_chunk
                logger.info(f"Using MAX_LEN_CHUNK from config: {max_chunk_size}")
            except Exception as e:
                logger.warning(f"Failed to get MAX_LEN_CHUNK from config, using default 6000: {e}")
                max_chunk_size = 6000

        # Protect image references so the translation LLM can't drop/mangle
        # them; restored once translation is done (see _protect_markdown_images).
        protected_md, image_refs = _protect_markdown_images(markdown_text)

        translate_stats = TranslationStats()
        translated_md = translate_chunks(
            protected_md,
            max_chunk_size=max_chunk_size,
            source_lang=source_lang,
            target_lang=target_lang,
            country=country,
            fast_mode=fast_mode,
            book_path=input_path,  # Enable vocabulary loading
            checkpoint_file=checkpoint_file,
            # Keep the checkpoint until build_output/validate_output below
            # actually succeed — a crash during EPUB assembly must not
            # discard a finished translation.
            remove_on_success=False,
            stats_out=translate_stats,
        )
        translated_md = _restore_markdown_images(translated_md, image_refs)

        if stats_out is not None:
            stats_out.total_source_len = translate_stats.total_source_len
            stats_out.total_target_len = translate_stats.total_target_len
            stats_out.total_chunks = translate_stats.total_chunks
            stats_out.failed_chunks = translate_stats.failed_chunks

        # Persist the finished translation before attempting to build the
        # output file — see _dump_translation's docstring.
        try:
            _dump_translation(translated_dump_path, meta_dump_path, translated_md,
                             metadata, translate_stats)
        except Exception as e:
            logger.warning(f"Failed to write translated-Markdown dump (non-fatal): {e}")

    # Step 4: Build output
    logger.info(f"Step 4/5: Building {output_format.upper()} output...")
    output_path = build_output(
        translated_md,
        output_format,
        metadata,
        images_dir=images_dir,
        input_path=input_path,
        target_lang=target_lang
    )

    # Step 5: Validate output
    if not skip_validation:
        logger.info("Step 5/5: Validating output file...")
        validation = validate_output(output_path, output_format)

        if validation.is_valid:
            logger.info(f"  ✓ {validation.summary()}")
        else:
            logger.error(f"  ✗ Validation failed:")
            for issue in validation.issues:
                logger.error(f"    [{issue.severity.upper()}] {issue.message}")
            _enforce_validation(validation, allow_invalid)
    else:
        logger.info("Step 5/5: Validation skipped (skip_validation=True)")

    # Output built (and validated, unless skipped) — the recovery artifacts
    # have done their job. If build_output or validation above raised, this
    # is never reached and both are left in place for the next run.
    if os.path.exists(checkpoint_file):
        try:
            os.remove(checkpoint_file)
        except OSError as e:
            logger.warning(f"Failed to remove checkpoint {checkpoint_file}: {e}")
    for dump_path in (translated_dump_path, meta_dump_path):
        if os.path.exists(dump_path):
            try:
                os.remove(dump_path)
            except OSError as e:
                logger.warning(f"Failed to remove {dump_path}: {e}")

    logger.info(f"Pipeline complete: {output_path}")
    return output_path
