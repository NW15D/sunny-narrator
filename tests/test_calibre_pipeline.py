"""
Tests for Calibre Pipeline.

Tests mock external dependencies (Calibre, pypandoc) to enable testing
without requiring those tools to be installed.
"""
import sys
import os
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

# Setup path
sys.path.insert(0, "/home/neo/prj/sunny-narrator")

# Mock third-party modules before importing calibre_pipeline
sys.modules['pypandoc'] = MagicMock()
sys.modules['pypandoc.convert_text'] = MagicMock()


def setup_mocks():
    """Setup all mocks for testing."""
    # Mock pypandoc
    import pypandoc
    pypandoc.convert_text = MagicMock(return_value="mocked markdown")
    pypandoc.convert_file = MagicMock(return_value="mocked file")
    
    return pypandoc


def test_check_calibre_installed_when_not_installed():
    """Test check_calibre_installed returns False when Calibre is not installed."""
    from src.calibre_pipeline import check_calibre_installed
    
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError()
        
        result = check_calibre_installed()
        
        assert result is False


def test_check_calibre_installed_when_installed():
    """Test check_calibre_installed returns True when Calibre is installed."""
    from src.calibre_pipeline import check_calibre_installed
    
    with patch('subprocess.run') as mock_run:
        mock_run.returncode = 0
        mock_run.return_value = MagicMock(returncode=0)
        
        result = check_calibre_installed()
        
        assert result is True


def test_calibre_pipeline_imports():
    """Test that calibre_pipeline imports successfully."""
    from src import calibre_pipeline
    
    assert hasattr(calibre_pipeline, 'convert_to_markdown')
    assert hasattr(calibre_pipeline, 'translate_chunks')
    assert hasattr(calibre_pipeline, 'build_output')
    assert hasattr(calibre_pipeline, 'run_pipeline')
    assert hasattr(calibre_pipeline, 'check_calibre_installed')
    assert hasattr(calibre_pipeline, 'TempDir')


def test_calibre_pipeline_exposed_functions():
    """Test that all expected functions are in __all__."""
    from src.calibre_pipeline import __all__
    
    expected = [
        'convert_to_markdown',
        'translate_chunks',
        'build_output',
        'run_pipeline',
        'check_calibre_installed',
        'TempDir',
    ]
    
    for func in expected:
        assert func in __all__, f"{func} not in __all__"


def test_temp_dir_context_manager():
    """Test that TempDir cleanup works."""
    from src.calibre_pipeline import TempDir
    
    with TempDir(prefix="test_") as temp_dir:
        # Create a test file
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        
        assert os.path.exists(temp_dir)
        assert os.path.exists(test_file)
    
    # After exiting, temp dir should be deleted
    assert not os.path.exists(temp_dir)


def test_extract_metadata_from_opf():
    """Test metadata extraction from OPF content."""
    from src.calibre_pipeline import extract_metadata_from_opf
    
    opf_content = """<?xml version="1.0" encoding="utf-8"?>
<package unique_identifier="uid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Test Book Title</dc:title>
    <dc:creator>Author Name</dc:creator>
    <dc:language>en</dc:language>
    <dc:publisher>Publisher Name</dc:publisher>
    <dc:description>Book description</dc:description>
  </metadata>
</package>"""
    
    metadata = extract_metadata_from_opf(opf_content)
    
    assert metadata["title"] == "Test Book Title"
    assert metadata["author"] == "Author Name"
    assert metadata["language"] == "en"
    assert metadata["publisher"] == "Publisher Name"
    assert metadata["description"] == "Book description"


def test_clean_calibre_markers():
    """Test Calibre marker removal."""
    from src.calibre_pipeline import _clean_calibre_markers
    
    text = """Some text<!-- 1 -->
More text
---
Even more text


Final text."""
    
    cleaned = _clean_calibre_markers(text)
    
    assert "<!--" not in cleaned
    assert "---" not in cleaned  # Should be replaced with newlines
    assert "Final text" in cleaned


def test_split_into_chunks_short_text():
    """Test chunk splitting for short text."""
    from src.calibre_pipeline import _split_into_chunks
    
    text = "Short text"
    chunks = _split_into_chunks(text, max_chunk_size=100)
    
    assert len(chunks) == 1
    assert chunks[0] == "Short text"


def test_split_into_chunks_long_text():
    """Test chunk splitting for long text."""
    from src.calibre_pipeline import _split_into_chunks
    
    # Create a long text that needs splitting
    text = "Word " * 500  # ~2500 chars
    chunks = _split_into_chunks(text, max_chunk_size=1000)
    
    # Should split into multiple chunks
    assert len(chunks) >= 2


def test_convert_to_markdown_not_installed():
    """Test convert_to_markdown raises FileNotFoundError when Calibre not installed."""
    from src.calibre_pipeline import convert_to_markdown
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=False):
        try:
            convert_to_markdown("fake.epub")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "Calibre" in str(e)


def test_convert_to_markdown_file_not_found():
    """Test convert_to_markdown raises FileNotFoundError for missing input."""
    from src.calibre_pipeline import convert_to_markdown
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True):
        try:
            convert_to_markdown("/nonexistent/file.epub")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "not found" in str(e).lower()


def test_translate_chunks_empty_text():
    """Test translate_chunks with empty text."""
    from src.calibre_pipeline import translate_chunks
    
    result = translate_chunks("")
    
    assert result == ""


def test_translate_chunks_returns_string():
    """Test translate_chunks returns a string."""
    from src.calibre_pipeline import translate_chunks
    
    with patch('src.utils.translate_chunk') as mock_translate:
        mock_translate.return_value = ("translated text", "outline")
        
        result = translate_chunks("some text", max_chunk_size=1000)
        
        assert isinstance(result, str)


def test_build_output_invalid_format():
    """Test build_output raises ValueError for invalid format."""
    from src.calibre_pipeline import build_output
    
    try:
        build_output("text", "invalid_format", {})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported" in str(e)


def test_build_output_not_installed():
    """Test build_output raises FileNotFoundError when Calibre not installed."""
    from src.calibre_pipeline import build_output
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=False):
        try:
            build_output("text", "fb2", {})
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "Calibre" in str(e)


def test_generate_title_page():
    """Test title page generation."""
    from src.calibre_pipeline import _generate_title_page
    
    metadata = {
        "title": "Test Book",
        "author": "Author Name",
        "publisher": "Publisher",
        "language": "en"
    }
    
    title_html = _generate_title_page(metadata)
    
    assert "<h1>Test Book</h1>" in title_html
    assert "by Author Name</h2>" in title_html
    assert "<p><em>Publisher</em></p>" in title_html
    assert "Language: en</p>" in title_html


def test_calibre_pipeline_module_exists():
    """Test that calibre_pipeline.py file exists."""
    file_path = "/home/neo/prj/sunny-narrator/src/calibre_pipeline.py"
    assert os.path.exists(file_path), f"calibre_pipeline.py not found at {file_path}"


def test_calibre_pipeline_has_required_functions():
    """Test that calibre_pipeline has all required functions with correct signatures."""
    import inspect
    from src import calibre_pipeline
    
    # Check convert_to_markdown signature
    sig = inspect.signature(calibre_pipeline.convert_to_markdown)
    assert 'input_path' in sig.parameters
    # Return annotation can be a type or empty
    assert sig.return_annotation is not inspect.Signature.empty
    
    # Check translate_chunks signature
    sig = inspect.signature(calibre_pipeline.translate_chunks)
    assert 'markdown_text' in sig.parameters
    assert 'max_chunk_size' in sig.parameters
    
    # Check build_output signature
    sig = inspect.signature(calibre_pipeline.build_output)
    assert 'translated_md' in sig.parameters
    assert 'output_format' in sig.parameters
    assert 'metadata' in sig.parameters


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])


# ===========================================================================
# Additional tests per design spec test list
# ===========================================================================


def test_convert_to_markdown_mocked():
    """Test full convert_to_markdown pipeline with mocked Calibre and pypandoc."""
    import zipfile
    from io import BytesIO
    from src.calibre_pipeline import convert_to_markdown
    
    opf_content = b"""<?xml version="1.0"?>
<package><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Mock Book</dc:title>
    <dc:creator>Mock Author</dc:creator>
    <dc:language>en</dc:language>
</metadata></package>"""
    
    html_content = b"<html><body><h1>Chapter 1</h1><p>Hello world</p></body></html>"
    
    # Create mock HTMLZ (zip) file
    htmlz_buffer = BytesIO()
    with zipfile.ZipFile(htmlz_buffer, 'w') as zf:
        zf.writestr('index.html', html_content)
        zf.writestr('metadata.opf', opf_content)
    htmlz_bytes = htmlz_buffer.getvalue()
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_subprocess, \
         patch('builtins.open', create=True), \
         patch('os.path.exists', return_value=True), \
         patch('zipfile.ZipFile') as mock_zipfile:
        
        # Mock subprocess for Calibre conversion
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # Mock ZipFile to return our test content
        mock_zf_instance = MagicMock()
        mock_zf_instance.namelist.return_value = ['index.html', 'metadata.opf']
        mock_zf_instance.read.side_effect = lambda name: html_content if name == 'index.html' else opf_content
        mock_zipfile.return_value.__enter__ = MagicMock(return_value=mock_zf_instance)
        mock_zipfile.return_value.__exit__ = MagicMock(return_value=False)
        
        # Mock pypandoc
        with patch('pypandoc.convert_text', return_value="# Chapter 1\n\nHello world"):
            md, metadata = convert_to_markdown("test.epub")
            
            assert md == "# Chapter 1\n\nHello world"
            assert metadata["title"] == "Mock Book"
            assert metadata["author"] == "Mock Author"
            assert metadata["language"] == "en"


def test_translate_chunks_unit():
    """Unit test for translate_chunks with mocked translate_chunk."""
    from src.calibre_pipeline import translate_chunks
    
    with patch('src.calibre_pipeline.translate_chunk') as mock_translate:
        mock_translate.return_value = ("переведённый текст", "synopsis")
        
        # Short text - single chunk
        result = translate_chunks("Hello world", max_chunk_size=1000)
        
        assert isinstance(result, str)
        assert mock_translate.call_count == 1


def test_translate_chunks_with_progress():
    """Test translate_chunks progress tracking with multiple chunks."""
    from src.calibre_pipeline import translate_chunks
    
    # Create text that will be split into multiple chunks
    long_text = "Chunk text. " * 500  # ~6500 chars
    
    with patch('src.calibre_pipeline.translate_chunk') as mock_translate:
        mock_translate.return_value = ("перевод", "synopsis")
        
        result = translate_chunks(long_text, max_chunk_size=2000)
        
        # Should have multiple translate calls
        assert mock_translate.call_count >= 2
        assert isinstance(result, str)


def test_translate_chunks_integration():
    """Integration test with mock book - verifies chunk→translate→reassemble flow."""
    from src.calibre_pipeline import translate_chunks
    
    mock_markdown = """# Chapter 1

Once upon a time, there was a dragon named Ignis who lived in a cave.
He liked to collect shiny things.

## Section 2

One day, a knight named Arthur came to visit the dragon."""
    
    translations = [
        ("# Глава 1\n\nЖил-был дракон по имени Игнис, который жил в пещере.\nОн любил собирать блестящие вещи.", "synopsis1"),
        ("## Раздел 2\n\nОднажды рыцарь по имени Артур пришёл навестить дракона.", "synopsis2"),
    ]
    
    call_count = 0
    def mock_translate(**kwargs):
        nonlocal call_count
        result = translations[call_count]
        call_count += 1
        return result
    
    with patch('src.calibre_pipeline.translate_chunk', side_effect=mock_translate):
        with patch('src.calibre_pipeline.split_text_smartly', side_effect=lambda t: (t[:len(t)//2], t[len(t)//2:])):
            result = translate_chunks(mock_markdown, max_chunk_size=150)
            
            assert call_count == 2
            assert "Глава 1" in result
            assert "дракон" in result


def test_build_output_epub():
    """Test EPUB output generation with mocked dependencies."""
    from src.calibre_pipeline import build_output
    
    metadata = {
        "title": "Test Book",
        "author": "Test Author",
        "language": "en"
    }
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('pypandoc.convert_text', return_value="<html><body>Test</body></html>") as mock_pandoc, \
         patch('subprocess.run') as mock_run, \
         patch('os.path.exists', return_value=True):
        
        mock_run.return_value = MagicMock(returncode=0)
        
        output_path = build_output(
            "# Translated Chapter\n\nHello world",
            "epub",
            metadata,
            output_path="/tmp/test_output.epub"
        )
        
        assert output_path == "/tmp/test_output.epub"
        # Verify pypandoc was called with TOC args
        assert mock_pandoc.call_count == 1
        call_args = mock_pandoc.call_args
        assert 'html' in str(call_args)
        assert 'toc' in str(call_args)


def test_build_output_fb2():
    """Test FB2 output generation with mocked dependencies."""
    from src.calibre_pipeline import build_output
    
    metadata = {
        "title": "Тестовая книга",
        "author": "Тестовый автор",
        "language": "ru"
    }
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('pypandoc.convert_text', return_value="<html><body>Тест</body></html>"), \
         patch('subprocess.run') as mock_run, \
         patch('os.path.exists', return_value=True):
        
        mock_run.return_value = MagicMock(returncode=0)
        
        output_path = build_output(
            "# Переведённая глава\n\nПривет мир",
            "fb2",
            metadata,
            output_path="/tmp/test_output.fb2"
        )
        
        assert output_path == "/tmp/test_output.fb2"
        # Verify Calibre was called with fb2 output file
        cmd_args = mock_run.call_args[0][0]
        assert "/tmp/test_output.fb2" in cmd_args
        assert "ebook-convert" in cmd_args


def test_full_pipeline_integration():
    """End-to-end mocked pipeline test: convert → translate → build."""
    from src.calibre_pipeline import run_pipeline
    
    import zipfile
    from io import BytesIO
    
    opf_content = b"""<?xml version="1.0"?>
<package><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Pipeline Test</dc:title>
</metadata></package>"""
    html_content = b"<html><body><p>Test content</p></body></html>"
    
    htmlz_buffer = BytesIO()
    with zipfile.ZipFile(htmlz_buffer, 'w') as zf:
        zf.writestr('index.html', html_content)
        zf.writestr('metadata.opf', opf_content)
    
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_subprocess, \
         patch('os.path.exists', return_value=True), \
         patch('zipfile.ZipFile') as mock_zipfile, \
         patch('pypandoc.convert_text') as mock_pandoc, \
         patch('src.calibre_pipeline.translate_chunk') as mock_translate, \
         patch('src.calibre_pipeline.split_text_smartly', return_value=("Test content", "")):
        
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_pandoc.return_value = "# Глава\n\nПереведённый текст"
        mock_translate.return_value = ("Переведённый текст", "synopsis")
        
        mock_zf_instance = MagicMock()
        mock_zf_instance.namelist.return_value = ['index.html', 'metadata.opf']
        mock_zf_instance.read.side_effect = lambda name: html_content if name == 'index.html' else opf_content
        mock_zipfile.return_value.__enter__ = MagicMock(return_value=mock_zf_instance)
        mock_zipfile.return_value.__exit__ = MagicMock(return_value=False)
        
        output = run_pipeline(
            input_path="/fake/book.epub",
            output_format="fb2",
            max_chunk_size=6000
        )
        
        assert isinstance(output, str)
        # Verify full pipeline was called
        assert mock_subprocess.call_count >= 2  # At least convert + output
        assert mock_translate.call_count >= 1


def test_error_handling():
    """Test error handling for various failure scenarios."""
    from src.calibre_pipeline import convert_to_markdown, build_output
    
    # Test 1: Unsupported input format
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            convert_to_markdown("test.pdf")
            assert False, "Should raise ValueError for PDF"
        except ValueError as e:
            assert "Unsupported input format" in str(e)
    
    # Test 2: Calibre conversion failure
    import subprocess
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        
        error = subprocess.CalledProcessError(1, "ebook-convert")
        error.stderr = "Conversion error: invalid format"
        mock_run.side_effect = error
        
        try:
            convert_to_markdown("test.epub")
            assert False, "Should raise ValueError on conversion failure"
        except ValueError as e:
            assert "Calibre conversion failed" in str(e)
    
    # Test 3: Calibre timeout
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        
        mock_run.side_effect = subprocess.TimeoutExpired("ebook-convert", 300)
        
        try:
            convert_to_markdown("test.epub")
            assert False, "Should raise ValueError on timeout"
        except ValueError as e:
            assert "timed out" in str(e).lower()


def test_pandoc_not_available():
    """Test error when pypandoc is not installed."""
    from src.calibre_pipeline import convert_to_markdown, PANDOC_AVAILABLE
    
    if PANDOC_AVAILABLE:
        # Only test when pypandoc IS available by patching it to False
        mock_zf_instance = MagicMock()
        mock_zf_instance.namelist.return_value = ['index.html', 'metadata.opf']
        mock_zf_instance.read.side_effect = lambda name: b'<html><body>test</body></html>' if name == 'index.html' else b'<?xml version="1.0"?><package></package>'
        
        with patch('src.calibre_pipeline.PANDOC_AVAILABLE', False), \
             patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
             patch('os.path.exists', return_value=True), \
             patch('subprocess.run') as mock_run, \
             patch('zipfile.ZipFile') as mock_zipfile:
            
            # Mock Calibre subprocess to avoid actual execution
            mock_run.return_value = MagicMock(returncode=0)
            mock_zipfile.return_value.__enter__ = MagicMock(return_value=mock_zf_instance)
            mock_zipfile.return_value.__exit__ = MagicMock(return_value=False)
            
            try:
                convert_to_markdown("test.epub")
                assert False, "Should raise FileNotFoundError when pypandoc not available"
            except FileNotFoundError as e:
                assert "pypandoc" in str(e).lower()


def test_translate_chunks_with_vocab_dict():
    """Test translate_chunks with explicit vocabulary dictionary."""
    from src.calibre_pipeline import translate_chunks
    
    vocab = {"dragon": "дракон", "knight": "рыцарь"}
    
    with patch('src.calibre_pipeline.translate_chunk') as mock_translate, \
         patch('src.calibre_pipeline.split_text_smartly', return_value=("dragon knight", "")):
        
        mock_translate.return_value = ("дракон рыцарь", "synopsis")
        
        result = translate_chunks("dragon knight", vocab_dict=vocab)
        
        # Verify vocab_dict was passed to translate_chunk
        call_kwargs = mock_translate.call_args[1]
        assert 'vocab_dict' in call_kwargs
