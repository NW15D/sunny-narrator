"""
Tests for Calibre Pipeline.

Tests mock external dependencies (Calibre, pypandoc) to enable testing
without requiring those tools to be installed.
"""
import sys
import os
from unittest.mock import MagicMock, patch
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# NOTE: pypandoc is a real installed dependency. Mocking it in sys.modules
# polluted every later test module that needs the real pypandoc (B4 incident).
# NOTE: bs4 is a real installed dependency (4.14.x). Mocking it in sys.modules
# polluted every later test module (isinstance() failures in bs4 internals).


def setup_mocks():
    """Setup all mocks for testing."""
    # Mock pypandoc
    import pypandoc
    pypandoc.convert_text = MagicMock(return_value="mocked markdown")
    pypandoc.convert_file = MagicMock(return_value="mocked file")
    
    # Mock BeautifulSoup
    from bs4 import BeautifulSoup
    BeautifulSoup.find_all = MagicMock(return_value=[])
    BeautifulSoup.get_text = MagicMock(return_value="")
    
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
    
    # C1/C4 fix: standalone --- (with blank line before) is removed;
    # setext-style --- (preceded by text, not a blank line) is preserved
    text = """Some text<!-- 1 -->
More text

---

Even more text


Final text."""
    
    cleaned = _clean_calibre_markers(text)
    
    assert "<!--" not in cleaned
    # Standalone --- (surrounded by blank lines) should be removed
    assert "---" not in cleaned
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
    """Test translate_chunks returns a string (5-stage pipeline)."""
    from src.calibre_pipeline import translate_chunks
    from unittest.mock import MagicMock
    
    # Mock _pipeline.execute to return a PipelineState-like object
    mock_state = MagicMock()
    mock_state.final_translation = "translated text"
    mock_state.synopsis = ""
    
    with patch('src.utils._pipeline.execute', return_value=mock_state):
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
            build_output("text", "docx", {})
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
    file_path = str(Path(__file__).resolve().parent.parent / "src" / "calibre_pipeline.py")
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


def test_convert_to_markdown_mocked(tmp_path):
    """Test full convert_to_markdown pipeline with mocked Calibre and pandoc.

    convert_to_markdown's HTML->Markdown step no longer calls
    pypandoc.convert_text() (that in-memory, timeout-less call is what
    stalled/OOM'd on a large real book — see _markdown_to_html_file's
    docstring in src/calibre_pipeline.py). It now shells out to the pandoc
    binary file-to-file via subprocess.run, same as the ebook-convert
    calls, so both are exercised through one subprocess.run side_effect
    that branches on cmd[0] — real files on disk, not mocked open()/exists.
    """
    import zipfile
    from src.calibre_pipeline import convert_to_markdown

    opf_content = b"""<?xml version="1.0"?>
<package><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Mock Book</dc:title>
    <dc:creator>Mock Author</dc:creator>
    <dc:language>en</dc:language>
</metadata></package>"""

    html_content = b"<html><body><h1>Chapter 1</h1><p>Hello world</p></body></html>"

    input_file = tmp_path / "test.epub"
    input_file.write_bytes(b"fake epub content")

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            # input -> HTMLZ (real zip on disk)
            with zipfile.ZipFile(cmd[2], 'w') as zf:
                zf.writestr('index.html', html_content)
                zf.writestr('metadata.opf', opf_content)
        else:
            # pandoc HTML -> Markdown (file-to-file, "-o <path>")
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write("# Chapter 1\n\nHello world")
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):
        md, metadata = convert_to_markdown(str(input_file))

        assert md == "# Chapter 1\n\nHello world"
        assert metadata["title"] == "Mock Book"
        assert metadata["author"] == "Mock Author"
        assert metadata["language"] == "en"


def test_translate_chunks_unit():
    """Unit test for translate_chunks with mocked _pipeline.execute."""
    from src.calibre_pipeline import translate_chunks
    
    # Mock _pipeline.execute to return a PipelineState-like object
    mock_state = MagicMock()
    mock_state.final_translation = "переведённый текст"
    mock_state.synopsis = "synopsis"
    
    with patch('src.utils._pipeline.execute', return_value=mock_state) as mock_execute:
        # Short text - single chunk
        result = translate_chunks("Hello world", max_chunk_size=1000)
        
        assert isinstance(result, str)
        assert mock_execute.call_count == 1


def test_translate_chunks_with_progress():
    """Test translate_chunks progress tracking with multiple chunks."""
    from src.calibre_pipeline import translate_chunks
    
    # Create text that will be split into multiple chunks
    # Use longer text with clear paragraph breaks
    long_text = """# Chapter 1

Once upon a time, there was a dragon named Ignis who lived in a cave. He liked to collect shiny things.

# Chapter 2

One day, a knight named Arthur came to visit the dragon.

# Chapter 3

They fought an epic battle and the knight emerged victorious.

# Chapter 4

After the battle, the dragon and knight became friends.

# Chapter 5

They lived happily ever after in the kingdom."""
    # ~1500 chars - enough to create multiple chunks at 6000 char limit
    # Actually, let's make it much longer to ensure chunking
    long_text = ("# Chapter " + "\n\n" + "text " * 2000 + "\n") * 3  # ~18000 chars
    
    # Mock _pipeline.execute to return a PipelineState-like object
    mock_state = MagicMock()
    mock_state.final_translation = "перевод"
    mock_state.synopsis = ""
    
    with patch('src.utils._pipeline.execute', return_value=mock_state) as mock_execute:
        result = translate_chunks(long_text, max_chunk_size=6000)
        
        # Should have multiple execute calls
        assert mock_execute.call_count >= 2, f"Expected >=2 calls, got {mock_execute.call_count}"
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
    def mock_execute(**kwargs):
        nonlocal call_count
        mock_state = MagicMock()
        mock_state.final_translation = translations[call_count][0]
        mock_state.synopsis = translations[call_count][1]
        call_count += 1
        return mock_state
    
    with patch('src.utils._pipeline.execute', side_effect=mock_execute):
        with patch('src.calibre_pipeline.split_text_smartly', side_effect=lambda t: (t[:len(t)//2], t[len(t)//2:])):
            result = translate_chunks(mock_markdown, max_chunk_size=150)
            
            assert call_count == 2
            assert "Глава 1" in result
            assert "дракон" in result


def test_build_output_epub(tmp_path):
    """Test EPUB output generation with mocked dependencies.

    build_output's Markdown->HTML step no longer calls pypandoc.convert_text
    (see _markdown_to_html_file's docstring for why) — it shells out to the
    pandoc binary file-to-file via subprocess.run, same channel as the
    ebook-convert call, so a single side_effect branching on cmd[0] covers
    both real subprocess invocations.
    """
    from src.calibre_pipeline import build_output

    metadata = {
        "title": "Test Book",
        "author": "Test Author",
        "language": "en"
    }

    output_path = str(tmp_path / "test_output.epub")
    calls = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ebook-convert":
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('EPUB content')
        else:
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write("<html><body>Test</body></html>")
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run):

        result = build_output(
            "# Translated Chapter\n\nHello world",
            "epub",
            metadata,
            output_path=output_path
        )

        assert result == output_path
        # One pandoc batch (Markdown -> HTML) + one ebook-convert call
        pandoc_calls = [c for c in calls if c[0] != "ebook-convert"]
        assert len(pandoc_calls) == 1
        assert '--wrap=none' in pandoc_calls[0]
        assert '-t' in pandoc_calls[0]
        assert 'html' in pandoc_calls[0]


def test_build_output_docx(tmp_path):
    """Test DOCX output generation with mocked dependencies."""
    from src.calibre_pipeline import build_output

    metadata = {
        "title": "Тестовая книга",
        "author": "Тестовый автор",
        "language": "ru"
    }

    output_path = str(tmp_path / "test_output.docx")

    def _fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ebook-convert":
            with open(cmd[2], 'w', encoding='utf-8') as f:
                f.write('DOCX content')
        else:
            out_path = cmd[cmd.index('-o') + 1]
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write("<html><body>Тест</body></html>")
        return MagicMock(returncode=0)

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run', side_effect=_fake_run) as mock_run:

        result = build_output(
            "# Переведённая глава\n\nПривет мир",
            "docx",
            metadata,
            output_path=output_path
        )

        assert result == output_path
        # Verify Calibre was called with docx output file
        ebook_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][0] == "ebook-convert"]
        assert len(ebook_calls) == 1
        assert output_path in ebook_calls[0]
        assert "ebook-convert" in ebook_calls[0]


def test_full_pipeline_integration(tmp_path):
    """End-to-end mocked pipeline test: convert → translate → build.

    Only check_calibre_installed and subprocess.run are mocked — everything
    else (zipfile, file I/O, os.path.exists) runs for real against real
    files in tmp_path. That now includes the two pandoc invocations
    (HTML<->Markdown), which moved from pypandoc.convert_text calls to
    subprocess.run just like the two ebook-convert calls, so the fake
    subprocess.run side_effect branches on cmd[0] instead of call count.
    """
    from src.calibre_pipeline import run_pipeline

    import zipfile

    opf_content = b"""<?xml version="1.0"?>
<package><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Pipeline Test</dc:title>
</metadata></package>"""
    html_content = b"<html><body><p>Test content</p></body></html>"

    # Mock _pipeline.execute to return a PipelineState-like object
    mock_state = MagicMock()
    mock_state.final_translation = "Переведённый текст"
    mock_state.synopsis = "synopsis"

    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_subprocess, \
         patch('src.utils._pipeline.execute', return_value=mock_state) as mock_execute, \
         patch('src.calibre_pipeline.translate_metadata', side_effect=lambda metadata, *a, **kw: dict(metadata)):
        # translate_metadata (used by run_pipeline's _translate_output_metadata
        # step) goes through LLMServiceCompat/llm_service directly, not
        # through _pipeline.execute, so it needs its own stub here to avoid
        # a real network call — identity pass-through keeps the title
        # ("Pipeline Test") unchanged for the filename assertion below.

        _fake_calls = {"ebook_convert": 0}

        def _fake_run(cmd, *args, **kwargs):
            if cmd[0] == "ebook-convert":
                _fake_calls["ebook_convert"] += 1
                out_path = cmd[2]
                if _fake_calls["ebook_convert"] == 1:
                    # Step 1 (convert_to_markdown): input -> HTMLZ
                    with zipfile.ZipFile(out_path, 'w') as zf:
                        zf.writestr('index.html', html_content)
                        zf.writestr('metadata.opf', opf_content)
                else:
                    # Step 4 (build_output): HTML/Markdown -> DOCX (real OOXML zip)
                    with zipfile.ZipFile(out_path, 'w') as zf:
                        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
                        zf.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX output content</w:t></w:r></w:p></w:body></w:document>')
            else:
                # A pandoc call: HTML->Markdown (convert_to_markdown) or
                # Markdown->HTML (build_output) — tell them apart via -t.
                out_path = cmd[cmd.index('-o') + 1]
                to_fmt = cmd[cmd.index('-t') + 1] if '-t' in cmd else ''
                content = ("# Глава\n\nПереведённый текст" if to_fmt == 'markdown'
                           else "<html><body>Переведённый текст</body></html>")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = _fake_run

        # convert_to_markdown checks os.path.exists(input_path) for real now
        # (no global os.path.exists patch) — needs an actual file on disk.
        input_path = tmp_path / "book.epub"
        input_path.write_bytes(b"fake epub content")

        output = run_pipeline(
            input_path=str(input_path),
            output_format="docx",
            max_chunk_size=6000,
            target_lang="russian"
        )

        assert isinstance(output, str)
        # Output is written next to the source file, with a language marker.
        assert os.path.dirname(output) == str(tmp_path)
        assert os.path.basename(output) == "Pipeline_Test_ru.docx"
        # Verify full pipeline was called: 2x ebook-convert + 2x pandoc
        assert mock_subprocess.call_count >= 4
        assert mock_execute.call_count >= 1

        # A successful run cleans up its checkpoint and translated-Markdown
        # dump (see run_pipeline's resume logic) — nothing should be left
        # over for the next run to (mis)interpret as a crash recovery.
        assert not (tmp_path / "book_ru.checkpoint.json").exists()
        assert not (tmp_path / "book_ru.translated.md").exists()
        assert not (tmp_path / "book_ru.meta.json").exists()

    # run_pipeline creates Pipeline_Test.docx in cwd; clean it up
    if os.path.exists("Pipeline_Test.docx"):
        os.remove("Pipeline_Test.docx")


def test_error_handling():
    """Test error handling for various failure scenarios."""
    from src.calibre_pipeline import convert_to_markdown
    
    # Test 1: Unsupported input format (FB2 is out of Calibre scope)
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('os.path.exists', return_value=True):
        try:
            convert_to_markdown("test.fb2")
            assert False, "Should raise ValueError for FB2"
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
    
    # Mock _pipeline.execute to return a PipelineState-like object
    mock_state = MagicMock()
    mock_state.final_translation = "дракон рыцарь"
    mock_state.synopsis = "synopsis"
    
    with patch('src.utils._pipeline.execute', return_value=mock_state) as mock_execute, \
         patch('src.calibre_pipeline.split_text_smartly', return_value=("dragon knight", "")):
        
        result = translate_chunks("dragon knight", vocab_dict=vocab)
        
        # Verify vocab_dict was passed to _pipeline.execute
        call_kwargs = mock_execute.call_args[1]
        assert 'vocab_dict' in call_kwargs
