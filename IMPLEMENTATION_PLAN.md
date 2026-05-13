# Implementation Plan: Feature Parity Completion for sunny-narrator (branch: markdown)

## Overview
This plan addresses the missing features identified in the Feature Parity Audit to bring the `New Pipeline` up to the level of the `Classic Pipeline`.

## Tasks

### 1. Rechunking Separator Fix
- [ ] Modify `~/prj/sunny-narrator/src/utils.py` at line 1430 to include `"\n\n"` between `result1` and `result2`.
- [ ] Verify with a quick test or manual inspection of the logic.

### 2. TOC Generation
- [ ] Locate the pandoc command invocation within `build_output()` in `~/prj/sunny-narrator/src/calibre_pipeline.py`.
- [ ] Append `--toc --toc-depth=2` to the pandoc arguments.
- [ ] Verify that the flag is correctly added to the list of arguments.

### 3. Image Preservation (High Complexity)
- [ ] **Phase A: Extraction**
    - [ ] In the pipeline where HTMLZ is handled, use `zipfile.ZipFile` to iterate through `zf.namelist()`.
    - [ ] Identify image files (jpg, png, etc.).
    - [ ] Extract images and store them as base64 strings in a metadata dictionary.
- [ ] **Phase B: Injection**
    - [ ] In `build_output()`, before the pandoc conversion, inject the extracted images into the HTML content.
    - [ ] Ensure images are properly embedded or referenced such that pandoc can process them.
- [ ] **Phase C: EPUB/FB2 Compatibility**
    - [ ] Convert HTML `<img src="...">` patterns back to a format compatible with the target output (e.g., `<image l:href="#id"/>` for FB2 if applicable, or ensure pandoc handles the base64/embedded images for EPUB).

## Verification Plan
- [ ] Run existing test suite (`pytest`) to ensure no regressions.
- [ ] (Optional) If possible, run a smoke test of the pipeline with an HTMLZ containing images.
- [ ] Verify TOC presence in generated EPUB/output.
