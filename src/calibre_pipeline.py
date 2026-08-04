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
    'ValidationIssue',
    'ValidationReport',
    'validate_epub',
    'validate_fb2',
    'validate_output',
    'extract_dictionary_from_md',
    'save_dictionary',
]

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
from src.utils import split_text_smartly, translate_chunk, num_tokens_in_string, config, validate_translation_length, _pipeline
from src.checkpoint_manager import CheckpointManager
from src.config import Config
from src import markdown_utils

# Precompiled Calibre-specific cleanup patterns (narrowed to avoid removing valid Pandoc attributes)
_RE_CALIBRE_COMMENT = re.compile(r'<!--\s*\d+\s*-->')
_RE_CALIBRE_SECTION_FULL = re.compile(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_CLASS = re.compile(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_BARE = re.compile(r'<[^>]*>:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_TRIPLE_COLON = re.compile(r':::')
_RE_CALIBRE_PARA = re.compile(r'<p>\s*\{#calibre[^}]*\}\s*</p>', re.DOTALL)
_RE_CALIBRE_ANCHOR = re.compile(r'\{#calibre[^}]*\}')  # Only calibre-specific anchors
_RE_CALIBRE_CLASS = re.compile(r'\{\.calibre\d*\}')  # Only calibre-specific classes
_RE_CALIBRE_ID_ATTR = re.compile(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', re.IGNORECASE)
_RE_CALIBRE_CLASS_ATTR = re.compile(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', re.IGNORECASE)
_RE_HR_MARKERS = re.compile(r'\n*---\s*\n*')
_RE_MULTI_BLANK = re.compile(r'\n{3,}')

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
    
    # Extract ISBN
    isbn_match = re.search(r'<dc:identifier[^>]*>([^<]+)</dc:identifier>', opf_content, re.IGNORECASE)
    if isbn_match:
        metadata["isbn"] = isbn_match.group(1).strip()
    
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
    if input_ext not in ['.epub', '.fb2', '.fbz']:
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
            
            try:
                _run_command(cmd, timeout=300)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if e.stderr else "Unknown error"
                stderr = stderr[:500]  # Limit for readability
                raise ValueError(f"Calibre conversion failed: {stderr}")
            except subprocess.TimeoutExpired:
                raise ValueError("Calibre conversion timed out")
            
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
            try:
                # Use --wrap=auto to prevent extremely long lines
                # This ensures better chunking behavior later
                markdown_text = pypandoc.convert_text(
                    html_content,
                    'markdown',
                    format='html',
                    extra_args=['--wrap=auto']
                )
            except Exception as e:
                raise ValueError(f"Pandoc conversion failed: {e}")
            
            # Step 5: Clean Calibre markers
            markdown_text = _clean_calibre_markers(markdown_text)
            
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
    checkpoint_file: Optional[str] = None
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
        if saved is not None and saved.get("book_path") == (book_path or ""):
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

        # Show progress
        progress = ((i + 1) / total_chunks) * 100
        print(f"\rProgress: {i + 1}/{total_chunks} ({progress:.1f}%)", end="", flush=True)
        
        # Translate chunk using 5-stage translation pipeline with retry
        translation = None
        for attempt in range(3):  # Up to 3 attempts
            try:
                state = _pipeline.execute(
                    source_lang=source_lang,
                    target_lang=target_lang,
                    source_text=chunk,
                    outline_text=outline_text,
                    vocab_dict=vocab_dict,
                    vocab_entries=vocab_entries,
                    country=country,
                    style=style,
                    fast_mode=fast_mode
                )
                
                translation = state.final_translation
                outline_text = state.synopsis or ""
                break  # Success
                
            except Exception as e:
                logger.warning(f"Translation attempt {attempt + 1} failed for chunk {i + 1} ({type(e).__name__}): {e}")
                if attempt < 2:
                    backoff = 2 ** (attempt + 1)  # 2s, 4s
                    logger.info(f"Retrying chunk {i + 1} in {backoff}s...")
                    time.sleep(backoff)
        
        if translation is not None:
            # Validate translation length
            is_valid, percent_diff, should_split = validate_translation_length(
                chunk, translation, f"chunk_{i+1}"
            )
            
            if not is_valid:
                logger.warning(f"Chunk {i+1} length validation failed ({percent_diff:.1f}% diff)")
            
            # Fallback: if translation is empty, keep original
            if not translation or not translation.strip():
                print(f"Empty translation for chunk {i + 1}, keeping original")
                translation = chunk
                failed_chunks += 1
        else:
            # All retries exhausted
            logger.error(f"All retries exhausted for chunk {i + 1}, keeping original")
            translation = chunk
            failed_chunks += 1
        
        translated_parts.append(translation)

        total_source_len += len(chunk)
        total_target_len += len(translation)

        # Save checkpoint after each chunk (D5)
        if checkpoint_mgr is not None:
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
    
    # All chunks done: drop the checkpoint so the next run starts fresh
    if checkpoint_mgr is not None:
        checkpoint_mgr.remove()

    # Reassemble translated text
    translated_text = '\n\n'.join(translated_parts)
    
    if logger:
        logger.info(f"Translation complete: {len(translated_text)} chars")
    else:
        print(f"Translation complete: {len(translated_text)} chars")
    
    return translated_text


def _split_into_chunks_md(text: str, max_chunk_size: int) -> list[str]:
    """Wrapper for markdown_utils.split_markdown_by_size."""
    return markdown_utils.split_markdown_by_size(text, target_size=max_chunk_size)


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


def build_output(
    translated_md: str,
    output_format: str,
    metadata: dict,
    output_path: Optional[str] = None,
    images_dir: Optional[str] = None
) -> str:
    """
    Build final output (FB2/EPUB) from translated Markdown.
    
    This function:
    1. Converts Markdown to HTML (with TOC) using pandoc
    2. Converts HTML to desired output format using Calibre
    3. Cleans up temporary files
    
    Args:
        translated_md: Translated Markdown content
        output_format: Output format - "fb2" or "epub"
        metadata: Book metadata dictionary
        output_path: Optional output path (auto-generated if not provided)
        
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
    # Simple heuristic: if more than 95% of content is English-like ASCII, might not be translated
    import re
    ascii_chars = len(re.findall(r'[a-zA-Z0-9]', translated_md))
    total_chars = len(translated_md)
    ascii_ratio = ascii_chars / total_chars if total_chars > 0 else 0
    
    if ascii_ratio > 0.95 and config.target_lang.lower() != 'english':
        logger.warning(f"High ASCII ratio ({ascii_ratio:.1%}) in translated markdown. "
                      f"May indicate translation failed or output not replaced properly.")
    
    output_format = output_format.lower()
    valid_formats = {'fb2', 'epub'}
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
        output_path = f"{safe_title}.{output_format}"
    
    with TempDir(prefix="calibre_output_") as temp_dir:
        try:
            # Step 1: Convert Markdown to HTML with TOC
            logger.info("Converting Markdown to HTML...")
            html_path = os.path.join(temp_dir, "output.html")
            
            # Add metadata as title page
            title_html = _generate_title_page(metadata)
            full_html = f"{title_html}\n\n{translated_md}"
            
            if not PANDOC_AVAILABLE:
                raise FileNotFoundError(
                    "pypandoc is not installed. "
                    "Install it: pip install pypandoc (requires pandoc: https://pandoc.org/installing.html)"
                )
            try:
                html_content = pypandoc.convert_text(
                    full_html,
                    'html',
                    format='markdown',
                    extra_args=['--wrap=none']
                )
            except Exception as e:
                raise ValueError(f"Pandoc HTML conversion failed: {e}")
            
            # Step 2b: Clean Calibre markers from HTML before conversion
            # This ensures no Calibre artifacts remain in the output
            logger.info("Cleaning Calibre markers from HTML...")
            html_content = _clean_calibre_markers(html_content)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # C8 fix: put book images next to the HTML so ebook-convert embeds them
            if images_dir and os.path.isdir(images_dir):
                import shutil
                for img_name in os.listdir(images_dir):
                    src_img = os.path.join(images_dir, img_name)
                    if os.path.isfile(src_img):
                        shutil.copy2(src_img, os.path.join(temp_dir, img_name))

            # Step 3: Convert HTML to output format using Calibre
            logger.info(f"Converting HTML to {output_format.upper()}...")
            cmd = [
                "ebook-convert",
                html_path,
                output_path,
            ]
            # C9 fix: pass metadata to Calibre so it lands in the output file
            if metadata.get('title'):
                cmd += ["--title", str(metadata['title'])]
            if metadata.get('author'):
                cmd += ["--authors", str(metadata['author'])]
            if metadata.get('language'):
                cmd += ["--language", str(metadata['language'])]
            
            try:
                _run_command(cmd, timeout=300)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if e.stderr else "Unknown error"
                stderr = stderr[:500]  # Limit for readability
                raise ValueError(f"Calibre output conversion failed: {stderr}")
            except subprocess.TimeoutExpired:
                raise ValueError("Calibre output conversion timed out")
            
            if not os.path.exists(output_path):
                raise ValueError(f"Output file was not created: {output_path}")
            
            # Step 4: Clean Calibre markers from output FB2 if output_format is fb2
            if output_format == 'fb2':
                logger.info("Cleaning Calibre markers from output FB2...")
                with open(output_path, 'r', encoding='utf-8') as f:
                    fb2_content = f.read()
                fb2_content = _clean_calibre_markers(fb2_content)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(fb2_content)
            
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
    title = metadata.get('title', 'Untitled')
    author = metadata.get('author', '')
    publisher = metadata.get('publisher', '')
    language = metadata.get('language', '')
    description = metadata.get('description', '')
    
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
                    if '<dc:creator>' not in opf_content:
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


def validate_output(output_path: str, output_format: str) -> ValidationReport:
    """
    Validate output file based on format.

    Dispatches to validate_epub() or validate_fb2() depending on format.

    Args:
        output_path: Path to output file
        output_format: "epub" or "fb2"

    Returns:
        ValidationReport with results
    """
    _init_logger()
    fmt = output_format.lower()
    if fmt == "epub":
        return validate_epub(output_path)
    elif fmt == "fb2":
        return validate_fb2(output_path)
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
                source_lang, target_lang, chunk, country, "Translate"
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


# Convenience function for full pipeline
def run_pipeline(
    input_path: str,
    output_format: str = "fb2",
    max_chunk_size: int = None,  # None = use MAX_LEN_CHUNK from config
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    fast_mode: bool = False,
    skip_validation: bool = False,
    allow_invalid: bool = False
) -> str:
    """
    Run the complete Calibre pipeline: convert -> translate -> build output -> validate.
    
    Args:
        input_path: Path to input EPUB/FB2 file
        output_format: Output format - "fb2" or "epub"
        max_chunk_size: Maximum chunk size for translation
        source_lang: Source language code
        target_lang: Target language code
        country: Target country for cultural context
        fast_mode: Skip reflection/improve stages
        skip_validation: Skip output validation step (for testing)
        
    Returns:
        Path to the generated output file
    """
    _init_logger()
    
    # Step 1: Convert to Markdown
    logger.info(f"Step 1/5: Converting {input_path} to Markdown...")
    markdown_text, metadata = convert_to_markdown(input_path)
    # C8: convert_to_markdown persisted images next to the input file
    images_dir = os.path.splitext(input_path)[0] + '_images'
    
    # Step 2: Translate
    logger.info("Step 2/5: Translating...")
    
    # Use MAX_LEN_CHUNK from config if max_chunk_size not specified
    if max_chunk_size is None:
        try:
            from src.config import Config
            config = Config()
            max_chunk_size = config.max_len_chunk
            logger.info(f"Using MAX_LEN_CHUNK from config: {max_chunk_size}")
        except Exception as e:
            logger.warning(f"Failed to get MAX_LEN_CHUNK from config, using default 6000: {e}")
            max_chunk_size = 6000
    
    translated_md = translate_chunks(
        markdown_text,
        max_chunk_size=max_chunk_size,
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        fast_mode=fast_mode,
        book_path=input_path  # Enable vocabulary loading
    )
    
    # Step 3: Build dictionary if .dic doesn't exist
    dic_path = Path(input_path).with_suffix('.dic')
    if not dic_path.exists():
        logger.info("Step 3/5: Building dictionary from source markdown...")
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
        logger.info(f"Step 3/5: Dictionary already exists: {dic_path} (skipped)")
    
    # Step 4: Build output
    logger.info(f"Step 4/5: Building {output_format.upper()} output...")
    output_path = build_output(
        translated_md,
        output_format,
        metadata,
        images_dir=images_dir
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
        logger.info("Step 4/4: Validation skipped (skip_validation=True)")
    
    logger.info(f"Pipeline complete: {output_path}")
    return output_path
