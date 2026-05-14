# Pipeline New Enhancements — Design (V2)

**Goal:** Расширить pipeline new функциональностью claude_translater

**Architecture:**
- Create `src/markdown_utils.py` for common functions
- Update `calibre_pipeline.py` to use markdown_utils
- Keep classic pipeline unchanged

**Components:**
- `markdown_utils.py`: chunk control, text validation, TOC, images, cleanup
- `calibre_pipeline.py`: orchestration, file I/O, pipeline control
- `src/utils.py`: existing pipeline (TranslationPipeline, validate_translation_length)

**Testing Strategy:**
- Unit tests for markdown_utils functions
- Integration tests for calibre_pipeline
- Feature parity tests vs classic pipeline

**Verified Dependencies:**
- `validate_translation_length` in utils.py (line 1416)
- `TranslationPipeline` class in utils.py (line 906)
- `_pipeline` instance in utils.py (line 1405)
- BeautifulSoup4 for TOC HTML parsing
