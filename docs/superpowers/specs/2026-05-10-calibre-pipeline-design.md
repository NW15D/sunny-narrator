# Calibre Pipeline Rewrite Design

**Goal:** Переработать pipeline sunny-narrator для поддержки EPUB/FB2 входных форматов через Calibre ebook-convert с использованием Existing chunking/translation functions.

**Architecture:** Создать `NewCalibrePipeline` класс (hybrid approach), который использует Calibre для conversion и existing functions (translate_chunk, vocabulary, NER) для translation. Добавить опцию в `app.py` для выбора pipeline.

**Tech Stack:**
- Calibre ebook-convert (EPUB/FB2 → HTMLZ → HTML → Markdown)
- pypandoc (HTML → Markdown)
- Existing: `utils.py`, `fb2_handler.py`, `epub_writer.py`
- Testing: pytest + mock

**Execution:** Use `subagent-driven-development` skill

---
## Components

### 1. `src/calibre_pipeline.py` (NEW)

**Responsibilities:**
- `convert_to_markdown(input_path: str) -> tuple[str, dict]` - Calibre → HTMLZ → HTML → Markdown, returns (markdown, metadata)
- `translate_chunks(markdown_text: str, max_chunk_size: int = 6000) -> str` - Chunk → Translate → Reassemble
- `build_output(translated_md: str, output_format: str, metadata: dict) -> str` - Markdown → FB2/EPUB

**Key Functions:**
```python
def convert_to_markdown(input_path: str) -> tuple[str, dict]:
    """Convert EPUB/FB2 to Markdown using Calibre
    
    Returns:
        (markdown_text, metadata): markdown content and book metadata
    
    Raises:
        FileNotFoundError: If Calibre is not installed
        ValueError: If conversion fails
    """
    # 1. Validate Calibre is installed
    # 2. Calibre ebook-convert → HTMLZ
    # 3. Extract HTML from HTMLZ
    # 4. HTML → Markdown via pypandoc
    # 5. Clean Calibre markers
    # 6. Extract metadata from HTMLZ metadata.opf
    # 7. Cleanup temp files
    pass

def translate_chunks(markdown_text: str, max_chunk_size: int = 6000) -> str:
    """Translate Markdown using existing translate_chunk
    
    Args:
        markdown_text: Markdown content to translate
        max_chunk_size: Maximum chunk size in chars (default 6000)
    """
    # 1. Split into chunks (utils.split_text_smartly)
    # 2. Translate each chunk (ta.translate_chunk)
    # 3. Reassemble with progress tracking
    pass

def build_output(translated_md: str, output_format: str, metadata: dict) -> str:
    """Build final output (FB2/EPUB)"
    # 1. Convert Markdown → HTML (pandoc with TOC)
    # 2. Calibre HTML → FB2/EPUB
    # 3. Cleanup temp files
    pass
```

### 2. `app.py` (MODIFY)

**Changes:**
- Add `--pipeline` argument (`classic|new`)
- Create `NewCalibrePipeline` instance
- Route to appropriate pipeline

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pipeline', choices=['classic', 'new'], default='classic')
    args = parser.parse_args()
    
    if args.pipeline == 'new':
        pipeline = NewCalibrePipeline(config)
        pipeline.run(input_file, output_format)
    else:
        # Classic pipeline (existing)
        pass
```

### 3. `tests/test_calibre_pipeline.py` (NEW)

**Responsibilities:**
- Test `convert_to_markdown()` (mock Calibre)
- Test `translate_chunks()` (mock translate_chunk)
- Test `build_output()` (mock pandoc/Calibre)
- Test full pipeline integration (mocked)

---
## File Structure

```
sunny-narrator/
├── src/
│   ├── calibre_pipeline.py    # NEW
│   ├── app.py                  # MODIFY
├── tests/
│   ├── test_calibre_pipeline.py  # NEW
│   └── test_integration.py     # EXISTING (keep)
```

---
## Data Flow

```
Input (EPUB/FB2)
    ↓
calibre_pipeline.convert_to_markdown()
    ↓ [Calibre → HTMLZ → HTML → Markdown + metadata]
Markdown Text + Metadata
    ↓
calibre_pipeline.translate_chunks(max_chunk_size=6000)
    ↓ [split → translate → reassemble + progress]
Translated Markdown
    ↓
calibre_pipeline.build_output(output_format='EPUB', metadata={...})
    ↓ [Markdown → HTML(TOC) → Calibre → EPUB]
Output (EPUB/FB2)
```

---
## Testing Strategy

**Approach:** Mock external dependencies (Calibre, pandoc)

**Test Cases:**
1. `test_convert_to_markdown_mocked` - Verify conversion pipeline with metadata
2. `test_translate_chunks_unit` - Unit test for chunking and translation
3. `test_translate_chunks_integration` - Integration test with mock book
4. `test_build_output_epub` - Verify EPUB generation
5. `test_build_output_fb2` - Verify FB2 generation
6. `test_full_pipeline_integration` - End-to-end (mocked)
7. `test_error_handling` - Verify Calibre not found errors

---
## Success Criteria

- [ ] `convert_to_markdown()` extracts metadata and returns `(markdown_text, metadata)` tuple
- [ ] Error handling for Calibre not installed/failed conversion with clear messages
- [ ] Temp files cleaned up via `finally:` or context manager
- [ ] `translate_chunks()` supports `max_chunk_size` parameter with default 6000
- [ ] Progress tracking for long books
- [ ] `build_output()` generates valid EPUB/FB2 with TOC
- [ ] All tests pass with mocked dependencies
- [ ] No breaking changes to existing pipeline
- [ ] `app.py` supports `--pipeline new` flag

---
## Dependencies

- Calibre (ebook-convert in PATH)
- pypandoc (`pip install pypandoc`)
- Existing: `markdown`, `beautifulsoup4` (for TOC generation)
- Existing: `fb2_handler`, `epub_writer`

---
## Migration Path

1. Create `src/calibre_pipeline.py` with all functions including error handling
2. Create `tests/test_calibre_pipeline.py` with mocked tests (including error handling tests)
3. Verify tests pass
4. Modify `app.py` to support `--pipeline` flag
5. Test with sample EPUB/FB2 files
6. Gradual deprecation of classic pipeline (if needed)

---
## Future Enhancements

- Add manifest.json validation (SHA-256)
- Support additional input formats (PDF, DOCX)
- Parallel subagents for chunk translation
- Resume support for long books
- Batch processing for multiple books
