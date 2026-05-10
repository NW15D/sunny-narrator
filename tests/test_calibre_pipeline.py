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
