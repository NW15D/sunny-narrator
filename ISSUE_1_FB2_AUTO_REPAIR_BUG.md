# Issue #1: FB2/EPUB Auto-Repair Causes Empty Body

## Status
**Open** - Auto-repair disabled pending fix

## Problem Description
When FB2 auto-repair is enabled, the final translated FB2 file has an empty `<body></body>` element, losing all translated content.

## Symptoms
- Temporary file (`*_tmp_*.fb2`) contains translated sections
- Final file (`*_ru_*.fb2`) has empty body
- Statistics show translation was performed (chars translated)
- No errors in logs during translation

## Example

### Temporary file (correct):
```xml
<section><title><p>Введение</p></title>
<p>Первый абзац главы «Введение».</p>
<p>Второй абзац главы «Введение».</p></section>
<section><title>
 <p>1. Глава первая. История формата FB2</p>
 </title>
 <p>Введение. Первый абзац</p>
 ...
```

### Final file (bug - empty body):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description>...</description>
<body>
</body>
</FictionBook>
```

## Root Cause Analysis

### Primary Issue: `rem_tags()` in Chunk Processing
The `rem_tags()` function in `src/xmlcheck.py` was being called during chunk processing (for each translated chunk), not just for final FB2 validation.

**Problematic code in `rem_tags()`:**
```python
# Ensure we have a single root for parsing
xml_string = xml_string.strip()
if not xml_string.startswith('<section'):
    wrapped_xml = f"<section>{xml_string}</section>"
else:
    wrapped_xml = xml_string  # <-- PROBLEM: No wrapper for multi-section input
```

When input starts with `<section` (which is always true for translated chunks), the XML is NOT wrapped in a container. But the input contains MULTIPLE `<section>` elements:

```xml
<section>...</section>
<section>...</section>
<section>...</section>
```

This is invalid XML (multiple root elements). The lxml parser with `recover=True` silently drops everything after the first element, losing most of the content.

### Secondary Issue: `rem_tags()` Used in Wrong Place
`rem_tags()` was called in:
1. `_post_process_xml()` - for each translated chunk
2. `process_all_chunks()` - during translation loop

This caused content loss during translation, before final FB2 assembly.

## Investigation Steps

1. **Confirmed translation works**: Temporary file contains full translation
2. **Identified loss point**: Content lost between temp file and final file
3. **Traced to `rem_tags()`**: Multiple sections caused parser to truncate
4. **Verified fix**: Wrapping always in container preserves all sections

## Attempted Fixes

### Fix 1: Always Wrap in Container (commit ce30809)
Changed `rem_tags()` to always wrap input in `<section>...</section>`:
```python
wrapped_xml = f"<section>{xml_string}</section>"
```

And unwrap after processing:
```python
if cleaned_xml.startswith('<section>') and cleaned_xml.endswith('</section>'):
    cleaned_xml = cleaned_xml[9:-10]
```

**Result**: Works for preserving sections, but `rem_tags()` still shouldn't be used on chunks.

### Fix 2: Remove `rem_tags()` from Chunk Processing (commit 466c391)
Replaced `rem_tags()` with basic cleanup in chunk processing:
```python
# Basic cleanup only - no XML parsing of chunks
section_content = final_content.strip()
```

**Result**: Correct approach - chunks preserved as-is from translator.

## Current State
- Auto-repair **disabled** (commit 43fc047)
- `rem_tags()` available for future final FB2 validation only
- Chunk processing uses basic cleanup without XML parsing

## Proposed Solution
1. Keep auto-repair **disabled** for now
2. When re-enabling:
   - Only use `rem_tags()` / `repair_and_validate()` on FINAL assembled FB2
   - Never use on individual chunks during translation
   - Ensure `rem_tags()` handles multiple sections correctly

## Files Affected
- `src/xmlcheck.py` - `rem_tags()` function
- `src/fb2_repair.py` - `repair_and_validate()` function
- `app.py` - chunk processing and file writing
- `src/fb2_handler.py` - `save_fb2()` function
- `src/epub_writer.py` - EPUB repair

## Related Commits
- `ce30809` - fix: Preserve all sections in rem_tags
- `6e77bbe` - chore: Disable FB2/EPUB auto-repair
- `466c391` - fix: Remove rem_tags from chunk processing
- `529a448` - chore: Re-enable auto-repair (reverted)
- `43fc047` - chore: Disable FB2/EPUB auto-repair (see issue #1)

## Testing Checklist
- [ ] Translate test book with auto-repair OFF
- [ ] Verify temp file has content
- [ ] Verify final FB2 has content in body
- [ ] Verify all sections present
- [ ] Test EPUB output
- [ ] After fix: test with auto-repair ON
