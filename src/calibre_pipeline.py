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
]

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

try:
    import pypandoc
    PANDOC_AVAILABLE = True
except ImportError:
    PANDOC_AVAILABLE = False
    pypandoc = None

# Import existing utilities
from src.utils import split_text_smartly, translate_chunk, num_tokens_in_string, config
from src.config import Config

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
                markdown_text = pypandoc.convert_text(
                    html_content,
                    'markdown',
                    format='html',
                    extra_args=['--wrap=none']
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
    
    Args:
        text: Markdown text with Calibre markers
        
    Returns:
        Cleaned text
    """
    if not text or not text.strip():
        return text
    
    # Remove Calibre comment markers like: <!-- 1 -->
    text = re.sub(r'<!--\s*\d+\s*-->', '', text)
    
    # Remove horizontal rules that are Calibre section markers
    text = re.sub(r'\n*---\s*\n*', '\n\n', text)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
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


def translate_chunks(
    markdown_text: str,
    max_chunk_size: int = 6000,
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    style: str = "text",
    fast_mode: bool = False,
    vocab_dict: Optional[dict] = None,
    book_path: Optional[str] = None
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
    
    # Split into chunks
    chunks = _split_into_chunks(markdown_text, max_chunk_size)
    total_chunks = len(chunks)
    
    if logger:
        logger.info(f"Translating {total_chunks} chunks (max_chunk_size={max_chunk_size})...")
    else:
        print(f"Translating {total_chunks} chunks (max_chunk_size={max_chunk_size})...")
    
    translated_parts = []
    outline_text = ""  # Context for next chunk
    
    # Load vocabulary if book_path provided and no explicit vocab_dict
    if vocab_dict is None and book_path:
        try:
            vocab_dict = _load_vocab_dict(book_path)
            if vocab_dict and logger:
                logger.info(f"Loaded vocabulary: {len(vocab_dict)} terms")
        except Exception as e:
            if logger:
                logger.warning(f"Failed to load vocabulary: {e}")
            else:
                print(f"Warning: Failed to load vocabulary: {e}")
            vocab_dict = {}
    elif vocab_dict is None:
        vocab_dict = {}
    
    for i, chunk in enumerate(chunks):
        # Show progress
        progress = ((i + 1) / total_chunks) * 100
        print(f"\rProgress: {i + 1}/{total_chunks} ({progress:.1f}%)", end="", flush=True)
        
        # Translate chunk
        try:
            translation, outline_text = translate_chunk(
                source_lang=source_lang,
                target_lang=target_lang,
                source_text=chunk,
                outline_text=outline_text,
                vocab_dict=vocab_dict,
                country=country,
                style=style,
                fast_mode=fast_mode,
                depth=0
            )
            
            # Fallback: if translation is empty, keep original
            if not translation or not translation.strip():
                print(f"Empty translation for chunk {i + 1}, keeping original")
                translation = chunk
            
            translated_parts.append(translation)
            
        except Exception as e:
            logger.error(f"Translation failed for chunk {i + 1}: {e}")
            # Keep original chunk on failure
            translated_parts.append(chunk)
    
    print()  # New line after progress
    
    # Reassemble translated text
    translated_text = '\n\n'.join(translated_parts)
    
    if logger:
        logger.info(f"Translation complete: {len(translated_text)} chars")
    else:
        print(f"Translation complete: {len(translated_text)} chars")
    
    return translated_text


def _split_into_chunks(text: str, max_chunk_size: int) -> list[str]:
    """
    Split text into chunks of approximately max_chunk_size.
    
    Uses split_text_smartly for respecting paragraph boundaries.
    
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
    output_path: Optional[str] = None
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
        # Sanitize filename
        safe_title = re.sub(r'[^\w\s-]', '', title).strip()[:50]
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
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Step 2: Convert HTML to output format using Calibre
            # Note: ebook-convert determines format from output file extension
            logger.info(f"Converting HTML to {output_format.upper()}...")
            cmd = [
                "ebook-convert",
                html_path,
                output_path,
            ]
            
            # Add metadata to Calibre command
            if metadata.get('title'):
                cmd.extend(["--title", metadata['title']])
            if metadata.get('author'):
                cmd.extend(["--author", metadata['author']])
            if metadata.get('language'):
                cmd.extend(["--language", metadata['language']])
            if metadata.get('publisher'):
                cmd.extend(["--publisher", metadata['publisher']])
            
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
    
    html = f"""<html>
<head>
    <title>{title}</title>
</head>
<body>
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
    
    html += "</body></html>"
    
    return html


# Convenience function for full pipeline
def run_pipeline(
    input_path: str,
    output_format: str = "fb2",
    max_chunk_size: int = 6000,
    source_lang: str = "en",
    target_lang: str = "ru",
    country: str = "Russia",
    fast_mode: bool = False
) -> str:
    """
    Run the complete Calibre pipeline: convert -> translate -> build output.
    
    Args:
        input_path: Path to input EPUB/FB2 file
        output_format: Output format - "fb2" or "epub"
        max_chunk_size: Maximum chunk size for translation
        source_lang: Source language code
        target_lang: Target language code
        country: Target country for cultural context
        fast_mode: Skip reflection/improve stages
        
    Returns:
        Path to the generated output file
    """
    _init_logger()
    
    # Step 1: Convert to Markdown
    logger.info(f"Step 1/3: Converting {input_path} to Markdown...")
    markdown_text, metadata = convert_to_markdown(input_path)
    
    # Step 2: Translate
    logger.info("Step 2/3: Translating...")
    translated_md = translate_chunks(
        markdown_text,
        max_chunk_size=max_chunk_size,
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        fast_mode=fast_mode,
        book_path=input_path  # Enable vocabulary loading
    )
    
    # Step 3: Build output
    logger.info(f"Step 3/3: Building {output_format.upper()} output...")
    output_path = build_output(
        translated_md,
        output_format,
        metadata
    )
    
    logger.info(f"Pipeline complete: {output_path}")
    return output_path
