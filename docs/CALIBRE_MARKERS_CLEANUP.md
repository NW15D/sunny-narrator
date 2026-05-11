# Calibre Markers Cleanup

## Overview

This document describes the Calibre-specific markers cleanup mechanism in Sunny Narrator's pipeline.

## Problem

When converting books through Calibre (`ebook-convert`), internal markers used for styling and structure remain in the output files. These markers appear in multiple forms:

### Types of Calibre Markers

1. **Block markers** (HTML format):
   ```html
   <div class="paragraph">:::{#calibre_link-0 .calibre}:::</div>
   <div class="paragraph">:::{.calibre1}### Annotation:::</div>
   ```

2. **Inline markers**:
   ```html
   <strong>Chapter 1</strong> {#calibre_link-7 .calibre9}
   ```

3. **Class attributes**:
   ```html
   <div class="calibre">
   <span class="calibre7">
   ```

4. **ID attributes**:
   ```html
   <div id="calibre_link-0">
   <div id="calibre_link-1">
   ```

5. **Standalone markers**:
   ```html
   :::
   {#annotation .calibre2}
   ```

## Solution

All Calibre markers are removed using the `_clean_calibre_markers()` function in `src/calibre_pipeline.py`.

### Pattern Matching

The cleanup function applies the following regex patterns in order:

1. **HTML comments**: `<!--\s*\d+\s*-->`
2. **Block markers**: `<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>`
3. **Class-only markers**: `<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>`
4. **Standalone ::::**: `<[^>]*>:::</[^>]*>` and standalone `:::`
5. **Inline markers with IDs**: `\{#[^}]+\}` (matches `{#calibre_link-0 .calibre}`, `{#annotation .calibre2}`, etc.)
6. **Class-only inline markers**: `\{\.\w+\}` (matches `{.calibre1}`, `{.paragraph}`, etc.)
7. **ID attributes**: `\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']`
8. **Class attributes**: `\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']`
9. **Horizontal rules**: `---` (section markers)
10. **Extra blank lines**: `\n{3,}` → `\n\n`

### Integration Points

The cleanup is applied at three key points in the pipeline:

#### 1. **Convert to Markdown** (`convert_to_markdown`)
```python
# After extracting HTML from HTMLZ, before Markdown conversion
html_content = _clean_calibre_markers(html_content)
markdown_text = pypandoc.convert_text(html_content, 'markdown', ...)
```

#### 2. **Build Output** (`build_output`)
```python
# Before converting Markdown to HTML
html_content = _clean_calibre_markers(html_content)

# After generating FB2 (for direct FB2→FB2 conversion)
if output_format == 'fb2':
    fb2_content = _clean_calibre_markers(fb2_content)
    with open(output_path, 'w') as f:
        f.write(fb2_content)
```

## Usage

### Command Line Tool

A standalone Python script `scripts/cleanup_calibre_markup.py` is available for manual cleanup:

```bash
# Test cleanup (output to stdout)
python scripts/cleanup_calibre_markup.py book.fb2

# In-place cleanup
python scripts/cleanup_calibre_markup.py book.fb2 --inplace
```

### Pipeline

When using the standard `run_pipeline()` function, cleanup is automatic:

```python
from src.calibre_pipeline import run_pipeline

output_path = run_pipeline(
    input_path="book.epub",
    output_format="fb2",
    source_lang="en",
    target_lang="ru"
)
# Output FB2 will have all Calibre markers removed
```

## Files

- **Main function**: `src/calibre_pipeline.py` - `_clean_calibre_markers()`
- **Cleanup script**: `scripts/cleanup_calibre_markup.py`
- **Test file**: `tests/test_calibre_cleanup.py`

## Testing

Run the test script to verify cleanup works correctly:

```bash
cd src
python ../tests/test_calibre_cleanup.py
```

Expected output:
```
=== FINAL CLEANUP CHECK ===
All markers removed ✓
```

## Examples

### Before Cleanup

```xml
<div class="paragraph">Пример книги</div>
<div class="paragraph">Введение</div>
<div class="paragraph"><strong class="calibre7">1. Глава первая</strong></div>
<div class="paragraph">:::{#calibre_link-0 .calibre}:::</div>
<div class="paragraph">Введение {#calibre_link-7 .calibre9} ============</div>
<div class="paragraph">First paragraph</div>
<div class="paragraph">:::</div>
```

### After Cleanup

```xml
<div>Пример книги</div>
<div>Введение</div>
<div><strong>1. Глава первая</strong></div>
<div>Введение ============</div>
<div>First paragraph</div>
```

## Troubleshooting

### Markers Still Present

If Calibre markers appear in the final output:

1. **Check conversion path**: Ensure you're using `run_pipeline()` or calling `_clean_calibre_markers()` explicitly
2. **Verify regex patterns**: Check that patterns in `_clean_calibre_markers()` match your markers
3. **Check file encoding**: Ensure UTF-8 encoding is used throughout

### Performance Issues

The cleanup function applies multiple regex passes. For large files:

- Consider processing in chunks
- The cleanup is still fast (<100ms for typical 1MB files)

## Future Improvements

Potential enhancements:

1. **Configuration**: Make cleanup patterns configurable via config file
2. **Logging**: Add detailed logging of removed markers for debugging
3. **Preservation**: Add option to preserve certain markers (e.g., for internal references)

## Related

- [FB2 Format Guide](../fb2_handler.py)
- [Installation Guide](INSTALLATION.md)
- [Translation Stages](TRANSLATION_STAGES.md)
