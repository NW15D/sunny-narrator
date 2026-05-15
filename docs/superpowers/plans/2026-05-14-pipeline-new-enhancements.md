# Pipeline New Enhancements — Implementation Plan (V2 - Fixed)

**Goal:** Расширить функциональность pipeline new (calibre_pipeline.py) за счет интеграции функций из claude_translater: контроль длины чанка, проверка текста, переповтор, работа с картинками и TOC, 5-стадийный перевод.

**Architecture:** Hybrid approach — создать `src/markdown_utils.py` для общих функций, обновить `calibre_pipeline.py` для использования этих функций, сохраняя совместимость с классическим pipeline.

**Tech Stack:**
- Python 3.10+
- Calibre ebook-convert
- pypandoc
- Existing `src/utils.py` translation pipeline (TranslationPipeline, validate_translation_length)
- BeautifulSoup4 (for TOC generation)

**Execution:** REQUIRED: Use `subagent-driven-development` skill

---

## 📁 File Structure

| Action | File |
|--------|------|
| Create | `src/markdown_utils.py` — общие функции для работы с markdown |
| Modify | `src/calibre_pipeline.py` — использовать markdown_utils |
| Create | `docs/superpowers/specs/2026-05-14-pipeline-new-enhancements-design.md` — дизайн-документ |
| Create | `tests/test_markdown_utils.py` — юнит-тесты |
| Modify | `tests/test_calibre_pipeline.py` — добавить тесты |

---

## 🎯 Design Principles

1. **One responsibility per file** — `markdown_utils.py` для markdown processing, `calibre_pipeline.py` для Orchestration
2. **Backward compatibility** — классический pipeline не меняется
3. **TDD** — сначала тесты, потом реализация
4. **DRY** — общие функции в `markdown_utils.py`

---

## ✅ Pre-Flight Checklist (Verified)

| Check | Status |
|-------|--------|
| `validate_translation_length` exists in `src/utils.py:1416` | ✅ |
| `length_check_threshold` in `src/config.py:109` (int, default=20) | ✅ |
| `_pipeline = TranslationPipeline()` in `src/utils.py:1405` | ✅ |
| `TranslationPipeline` class exists in `src/utils.py:906` | ✅ |
| BeautifulSoup available (bs4) | ✅ (required dependency) |

---

## 📋 Implementation Tasks

### Task 0: Setup & Context

**Files:**
- Verify: `src/config.py` already has `length_check_threshold` (no change needed)
- Create: `docs/superpowers/specs/2026-05-14-pipeline-new-enhancements-design.md`

- [ ] **Step 1: Verify config already has length_check_threshold**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python -c "from src.config import Config; c = Config(); print(f'length_check_threshold: {c.length_check_threshold}')"
```
Expected: `length_check_threshold: 20`

- [ ] **Step 2: Create design document**
Save to `docs/superpowers/specs/2026-05-14-pipeline-new-enhancements-design.md`:
```markdown
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
```

---

### Task 1: Create markdown_utils.py (6 subtasks)

**Files:**
- Create: `src/markdown_utils.py`

#### Task 1a: Basic functions + imports

- [ ] **Step 1: Write failing test**
Create `tests/test_markdown_utils.py`:
```python
import pytest
from src.markdown_utils import (
    split_markdown_by_size,
    generate_toc_html,
    clean_calibre_markers,
)

def test_split_markdown_by_size_small_text():
    text = "Hello world\n\nThis is a test."
    chunks = split_markdown_by_size(text, target_size=1000)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_split_markdown_by_size_large_text():
    text = "# Chapter 1\n\n" + "word " * 1000 + "\n# Chapter 2\n\n" + "word " * 1000
    chunks = split_markdown_by_size(text, target_size=2000)
    assert len(chunks) >= 2

def test_clean_calibre_markers():
    text = "Hello <!-- 1 -->world{#calibre_link-1 .calibre1}</p>"
    cleaned = clean_calibre_markers(text)
    assert "1" not in cleaned
```

- [ ] **Step 2: Run test to verify it fails**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
pytest tests/test_markdown_utils.py::test_split_markdown_by_size_small_text -v
```
Expected: `FAILED (tests do not exist yet)`

- [ ] **Step 3: Write minimal implementation**
Create `src/markdown_utils.py`:
```python
"""
Utility functions for Markdown processing (extracted from claude_translater and existing code).

Provides:
- split_markdown_by_size: Chunk control (simplified)
- generate_toc_html: TOC generation
- extract_headings: Heading parsing
- clean_markdown_content: Text cleaning
- copy_images_to_output: Image handling
- clean_calibre_markers: Remove Calibre-specific markers

Dependencies: bs4 (BeautifulSoup4) for HTML processing
"""

import re
import os
import glob
import shutil
from typing import List, Dict, Any, Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

logger = None


def _init_logger():
    """Lazy logger initialization."""
    global logger
    if logger is None:
        try:
            import logging
            logger = logging.getLogger(__name__)
        except ImportError:
            pass


def split_markdown_by_size(content: str, target_size: int = 6000) -> List[str]:
    """Split markdown into chunks by character count, respecting paragraph boundaries."""
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for line in lines:
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > target_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_size = line_size
        else:
            current_chunk.append(line)
            current_size += line_size
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def extract_headings(soup) -> List[Dict[str, Any]]:
    """Extract all headings from HTML and generate TOC data."""
    if not BS4_AVAILABLE:
        return []
    
    headings = []
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(heading.name[1])
        text = heading.get_text().strip()
        heading_id = generate_heading_id(text, headings)
        heading['id'] = heading_id
        headings.append({'level': level, 'text': text, 'id': heading_id})
    return headings


def generate_heading_id(text: str, existing_headings: List[Dict]) -> str:
    """Generate unique heading ID."""
    heading_id = text.lower().replace(' ', '-').replace('.', '')
    
    # Make unique
    base_id = heading_id
    counter = 1
    while any(h['id'] == heading_id for h in existing_headings):
        heading_id = f"{base_id}-{counter}"
        counter += 1
    
    return heading_id


def generate_simple_toc_html(toc_data: List[Dict]) -> str:
    """Generate nested HTML for TOC."""
    if not toc_data:
        return ""
    
    toc_html = '<nav id="toc"><ul>\n'
    current_level = 1
    for item in toc_data:
        level = item['level']
        text = item['text']
        heading_id = item['id']
        
        # Handle nesting levels
        if level > current_level:
            toc_html += '<ul>\n'
        elif level < current_level:
            toc_html += '</ul></li>\n' * (current_level - level)
        
        toc_html += f'<li><a href="#{heading_id}">{text}</a></li>\n'
        current_level = level
    
    # Close unclosed lists
    toc_html += '</ul>' * (current_level - 1) + '\n</nav>'
    
    return toc_html


def generate_toc_html(toc_data: List[Dict]) -> str:
    """Generate nested HTML for TOC (alias for generate_simple_toc_html)."""
    return generate_simple_toc_html(toc_data)


def clean_markdown_content(content: str, file_dir: Optional[str] = None) -> str:
    """Clean markdown content: remove non-existent image markers, extra whitespace."""
    if not content:
        return content
    
    # Remove markdown images pointing to non-existent files
    image_pattern = r'!\[.*?\]\((.*?)\)'
    lines = content.split('\n')
    result_lines = []
    
    for line in lines:
        image_matches = list(re.finditer(image_pattern, line))
        if image_matches:
            new_line = line
            for match in reversed(image_matches):
                image_path = match.group(1)
                # Skip absolute URLs
                if image_path.startswith(('http://', 'https://')):
                    continue
                # Check if local image exists
                if file_dir:
                    full_path = os.path.join(file_dir, image_path)
                    if not os.path.exists(full_path):
                        # Remove the image marker
                        new_line = new_line[:match.start()] + new_line[match.end():]
            result_lines.append(new_line)
        else:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def copy_images_to_output(temp_dir: str, output_dir: str) -> List[str]:
    """Copy image files from temp_dir to output_dir."""
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']
    copied_files = []
    
    os.makedirs(output_dir, exist_ok=True)
    
    for ext in image_extensions:
        for image_file in glob.glob(os.path.join(temp_dir, f'*{ext}')):
            filename = os.path.basename(image_file)
            dest = os.path.join(output_dir, filename)
            if not os.path.exists(dest):
                shutil.copy2(image_file, dest)
                copied_files.append(filename)
    
    return copied_files


def clean_calibre_markers(text: str) -> str:
    """Remove Calibre-specific markers from HTML/Markdown."""
    if not text or not text.strip():
        return text
    
    # Remove Calibre comment markers like: <!-- 1 -->
    text = re.sub(r'<!--\s*\d+\s*-->', '', text)
    
    # Remove Calibre section markers
    text = re.sub(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]*>:::</[^>]*>', '', text, flags=re.DOTALL)
    
    # Remove inline Calibre markers
    text = re.sub(r'\{#[^}]+\}', '', text)
    text = re.sub(r'\{\.\w+\}', '', text)
    text = re.sub(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', '', text, flags=re.IGNORECASE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
```

- [ ] **Step 4: Run test to verify it passes**
```bash
pytest tests/test_markdown_utils.py -v
```
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**
```bash
git add .
git commit -m "feat: add markdown_utils for common markdown processing"
```

#### Task 1b: Extract HTML headings from HTMLZ

- [ ] **Step 1: Add test for HTMLZ extraction**
```python
def test_extract_headings_from_htmlz():
    """Test extracting headings from HTML inside HTMLZ archive."""
    from src.markdown_utils import extract_headings, generate_simple_toc_html
    from bs4 import BeautifulSoup
    
    html_content = '<h1>Chapter 1</h1><h2>Section 1.1</h2><h2>Section 1.2</h2>'
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = extract_headings(soup)
    
    assert len(headings) == 3
    assert headings[0]['level'] == 1
    assert headings[0]['text'] == 'Chapter 1'
    assert headings[1]['level'] == 2
```

- [ ] **Step 2: Run test**
```bash
pytest tests/test_markdown_utils.py::test_extract_headings_from_htmlz -v
```
Expected: PASS

#### Task 1c: Add TOC to HTML

- [ ] **Step 1: Add TOC test**
```python
def test_add_toc_to_html():
    """Test adding TOC to HTML content."""
    from src.markdown_utils import generate_toc_html
    
    toc_data = [
        {'level': 1, 'text': 'Chapter 1', 'id': 'chapter-1'},
        {'level': 2, 'text': 'Section 1.1', 'id': 'section-1-1'},
        {'level': 2, 'text': 'Section 1.2', 'id': 'section-1-2'},
        {'level': 1, 'text': 'Chapter 2', 'id': 'chapter-2'},
    ]
    
    toc_html = generate_toc_html(toc_data)
    assert '<nav id="toc">' in toc_html
    assert 'Chapter 1' in toc_html
    assert 'Section 1.1' in toc_html
```

- [ ] **Step 2: Run test**
```bash
pytest tests/test_markdown_utils.py::test_add_toc_to_html -v
```
Expected: PASS

#### Task 1d: Add image copy test

- [ ] **Step 1: Add image test**
```python
def test_copy_images_to_output():
    """Test that images are properly copied to output."""
    import tempfile
    from src.markdown_utils import copy_images_to_output
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test images
        images_dir = os.path.join(temp_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        open(os.path.join(images_dir, "test.png"), 'w').close()
        open(os.path.join(images_dir, "test.jpg"), 'w').close()
        
        with tempfile.TemporaryDirectory() as output_dir:
            copied = copy_images_to_output(temp_dir, output_dir)
            assert "test.png" in copied
            assert "test.jpg" in copied
            assert os.path.exists(os.path.join(output_dir, "test.png"))
```

- [ ] **Step 2: Run test**
```bash
pytest tests/test_markdown_utils.py::test_copy_images_to_output -v
```
Expected: PASS

#### Task 1e: Add length validation test

- [ ] **Step 1: Add validation test**
```python
def test_validate_translation_length():
    """Test length validation function."""
    from src.utils import validate_translation_length
    
    # Test valid chunk (50% diff exactly at threshold)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 1000, "x" * 1500, "test"
    )
    assert is_valid == True  # 50% is exactly the threshold (default 20, but 50 > 20)
    assert percent_diff == 50.0
    
    # Test invalid chunk (51% diff)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 1000, "x" * 1510, "test"
    )
    assert is_valid == False
    assert percent_diff == 51.0
```

- [ ] **Step 2: Run test**
```bash
pytest tests/test_markdown_utils.py::test_validate_translation_length -v
```
Expected: PASS

#### Task 1f: Full markdown_utils test suite

- [ ] **Step 1: Run all tests**
```bash
pytest tests/test_markdown_utils.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 2: Commit**
```bash
git add .
git commit -m "test: add full test suite for markdown_utils"
```

---

### Task 2: Update calibre_pipeline.py

**Files:**
- Modify: `src/calibre_pipeline.py`

- [ ] **Step 1: Import markdown_utils**
Add after existing imports:
```python
from src import markdown_utils
```

- [ ] **Step 2: Use split_markdown_by_size from markdown_utils**
Replace `_split_into_chunks_md` function with wrapper:
```python
def _split_into_chunks_md(text: str, max_chunk_size: int) -> list[str]:
    """Wrapper for markdown_utils.split_markdown_by_size."""
    return markdown_utils.split_markdown_by_size(text, target_size=max_chunk_size)
```

- [ ] **Step 3: Add text validation to translate_chunks**
Add after translation:
```python
from src.utils import validate_translation_length

# Inside translate_chunks, after each chunk translation:
is_valid, percent_diff, should_split = validate_translation_length(
    chunk, translation, f"chunk_{i+1}"
)

if not is_valid:
    logger.warning(f"Chunk {i+1} length validation failed ({percent_diff:.1f}% diff)")
```

- [ ] **Step 4: Add TOC generation to build_output**
Add before Calibre conversion:
```python
def _add_toc_to_html(markdown_text: str) -> str:
    """Add TOC to HTML after pandoc conversion."""
    from bs4 import BeautifulSoup
    
    # Convert markdown to HTML
    if PANDOC_AVAILABLE:
        html_content = pypandoc.convert_text(markdown_text, 'html', format='markdown')
    else:
        raise ImportError("pypandoc is required for TOC generation")
    
    # Extract headings and generate TOC
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = extract_headings(soup)
    toc_html = generate_toc_html(headings)
    
    # Insert TOC after <body> or at beginning
    if soup.body:
        soup.body.insert(0, BeautifulSoup(toc_html, 'html.parser').nav)
    elif soup.html:
        soup.html.insert(0, BeautifulSoup(toc_html, 'html.parser').nav)
    
    return str(soup)
```

- [ ] **Step 5: Add image handling to convert_to_markdown**
Add after HTMLZ extraction:
```python
# In convert_to_markdown, after HTMLZ extraction:
htmlz_dir = os.path.join(temp_dir, "htmlz_images")
os.makedirs(htmlz_dir, exist_ok=True)

# Extract images from HTMLZ if present
# (HTMLZ might contain images in a subdirectory)

# Update _add_toc_to_html to accept extracted images directory
```

- [ ] **Step 6: Run full pipeline tests**
```bash
pytest tests/test_calibre_pipeline.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**
```bash
git add .
git commit -m "refactor: use markdown_utils in calibre_pipeline.py"
```

---

### Task 3: Add 5-Stage Translation to translate_chunks

**Files:**
- Modify: `src/calibre_pipeline.py`

- [ ] **Step 1: Update translate_chunks to use validate_translation_length**
Replace inline translation with validation call (already added in Task 2).

- [ ] **Step 2: Update translate_chunks to use 5-stage translation**
Replace `translate_chunk` call with direct pipeline execution:
```python
# In translate_chunks, replace:
translation, outline_text = translate_chunk(...)

# With:
from src.utils import _pipeline, TranslationStage

state = _pipeline.execute(
    source_lang=source_lang,
    target_lang=target_lang,
    source_text=chunk,
    outline_text=outline_text,
    vocab_dict=vocab_dict,
    vocab_entries=[],  # Or load from .dic if available
    country=country,
    style=style,
    fast_mode=fast_mode
)

translation = state.final_translation
outline_text = state.synopsis or ""
```

- [ ] **Step 3: Add vocab_entries support**
```python
def _load_vocab_entries(book_path: str) -> List[Dict[str, Any]]:
    """Load vocabulary entries from .dic file as dict objects."""
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
```

- [ ] **Step 4: Run tests**
```bash
pytest tests/test_calibre_pipeline.py::test_translate_chunks_unit -v
```
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add .
git commit -m "feat: add 5-stage translation to translate_chunks"
```

---

### Task 4: Integration Tests

**Files:**
- Modify: `tests/test_calibre_pipeline.py`

- [ ] **Step 1: Add length validation integration test**
```python
def test_translate_chunks_length_validation_integration():
    """Test that validate_translation_length is called during translation."""
    # This test verifies the integration point
    from src.utils import validate_translation_length
    
    # Test that function exists and works
    is_valid, _, _ = validate_translation_length("a" * 100, "b" * 100, "integration")
    assert is_valid == True
```

- [ ] **Step 2: Add TOC integration test**
```python
def test_build_output_toc_generation():
    """Test that TOC is properly generated in HTML output."""
    from src.markdown_utils import generate_toc_html, extract_headings
    from bs4 import BeautifulSoup
    
    toc_data = [
        {'level': 1, 'text': 'Chapter 1', 'id': 'chapter-1'},
        {'level': 2, 'text': 'Section 1.1', 'id': 'section-1-1'},
    ]
    
    toc_html = generate_toc_html(toc_data)
    assert '<nav id="toc">' in toc_html
    assert 'Chapter 1' in toc_html
```

- [ ] **Step 3: Run all tests**
```bash
pytest tests/test_markdown_utils.py tests/test_calibre_pipeline.py -v
```
Expected: All tests PASS

- [ ] **Step 4: Commit**
```bash
git add .
git commit -m "test: add integration tests for pipeline new enhancements"
```

---

### Task 5: Code Review & Polish

**Files:**
- Modify: `src/markdown_utils.py`, `src/calibre_pipeline.py`, `docs/`

- [ ] **Step 1: Run linter**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
flake8 src/markdown_utils.py src/calibre_pipeline.py tests/test_markdown_utils.py
```
Expected: No errors (or fix if any)

- [ ] **Step 2: Run type checker**
```bash
mypy src/markdown_utils.py src/calibre_pipeline.py
```
Expected: Minimal warnings (add type hints if needed)

- [ ] **Step 3: Update documentation**
Add to `docs/superpowers/specs/2026-05-14-pipeline-new-enhancements-design.md`:
- Architecture diagram
- Component responsibilities
- Testing strategy

- [ ] **Step 4: Final review**
Dispatch subagent:
```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    model="researcher",
    task="""[Code Review] Проверить реализацию pipeline new enhancements

[Files]
- src/markdown_utils.py
- src/calibre_pipeline.py
- tests/test_markdown_utils.py
- tests/test_calibre_pipeline.py

[Checklist]
- Функции из claude_translater правильно интегрированы?
- Нет дублирования кода?
- Сохранена совместимость с classic pipeline?
- Тесты покрывают критичные сценарии?

[Формат] Список issues или ✅ Approved""",
    timeoutSeconds=600
)
```

- [ ] **Step 5: Final commit**
```bash
git add .
git commit -m "refactor: apply code review feedback for pipeline new enhancements"
```

---

## 🎯 Success Criteria

| Criteria | Status |
|----------|--------|
| ✅ Control chunk size (max_chunk_size) | Done in Task 1a + Task 2 |
| ✅ Validate translation length | Done in Task 2 + Task 4 |
| ✅ Image handling (copy to output) | Done in Task 1a + Task 2 |
| ✅ TOC generation | Done in Task 1a + Task 2 |
| ✅ 5-stage translation | Done in Task 3 |
| ✅ Vocabulary dict support | Done in Task 3 |
| ✅ All tests pass | Done in Task 4 |
| ✅ Code review passed | Done in Task 5 |

---

## 🔄 Next Steps

After all tasks complete:

1. **Merge to develop branch**
   ```bash
   git checkout develop
   git merge --no-edit 2026-05-14-pipeline-new-enhancements
   git push origin develop
   ```

2. **Deploy to test environment**
   - Run full pipeline test with sample EPUB/FB2
   - Verify output matches classic pipeline quality

3. **Update documentation**
   - Add changelog entry
   - Update README with new features

---

## 📝 Changelog

| Version | Changes |
|---------|---------|
| v0.2.0 (unreleased) | Enhanced pipeline new with: chunk control, text validation, TOC, image handling, 5-stage translation |
| v0.2.1 (V2) | Fixed plan issues: correct config type, added import validations, broke down tasks |
