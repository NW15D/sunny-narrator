# Plan: Add Keyword Extraction to NER Vocabulary

**Date:** 2026-04-28  
**Trigger:** User request to add spaCy-based keyword extraction  
**Status:** TODO

---

## Overview

Add keyword extraction using spaCy to improve vocabulary collection:
1. Extract keywords by frequency (tokens that are not stop words, are alpha)
2. Extract keywords by semantic weight (tokens with vector_norm > 0)
3. Merge into existing vocabulary array
4. Clean/merge using spaCy tools

---

## Tasks

### Task 1: Add keyword extraction function

**File:** `src/ner.py`  
**Function:** `extract_keywords_from_text(text: str) -> list[str]`  
**Action:**
- Create new function that uses spaCy
- Extract: `keywords_freq = [token.text for token in doc if not token.is_stop and token.is_alpha]`
- Extract: `keywords_semantic = [token.text for token in doc if not token.is_stop and token.vector_norm > 0]`
- Return combined list of keywords

**Priority:** HIGH

---

### Task 2: Integrate keywords into make_vocab()

**File:** `src/ner.py`  
**Function:** `make_vocab()`  
**Action:**
- Call `extract_keywords_from_text()` after NER processing
- Merge keywords into existing vocabulary (Counter)
- Keep existing NER + word extraction unchanged

**Priority:** HIGH

---

### Task 3: Add tests

**File:** `tests/test_ner_keywords.py` (new)  
**Action:**
- Test keyword extraction function
- Test integration with make_vocab
- Test that keywords are properly merged

**Priority:** MEDIUM

---

## Acceptance Criteria

1. Keywords extracted using spaCy are added to vocabulary
2. Existing NER functionality unchanged
3. Tests pass
4. Code follows existing patterns in ner.py

---

## References

- Current: `src/ner.py` (make_vocab, create_series_vocab)
- User example:
```python
keywords_freq = [token.text for token in doc if not token.is_stop and token.is_alpha]
keywords_semantic = [token.text for token in doc if not token.is_stop and token.vector_norm > 0]
```
