# Vocabulary Matching Fix Implementation Plan

**Goal:** Fix critical bug where dictionary terms don't appear in chunk vocabulary, and clean up formatting with trailing commas.

**Architecture:** Two-stage matching: (1) exact text search for presence check, (2) cosine similarity for semantic matches. Clean up formatting to remove trailing empty commas.

**Tech Stack:** Python, spaCy, CuPy/NumPy, pytest

**Execution:** REQUIRED: Use `subagent-driven-development` or `executing-plans` skill

---

## Task Structure

### Task 0: Write test for exact text match (Stage 1)

**Files:**
- Create: `tests/test_vocab_matching.py`

**Goal:** Test that exact substring match works for dictionary terms in chunk text.

- [ ] **Step 1: Write the failing test**
```python
#!/usr/bin/env python3
"""
Test vocabulary matching with exact text search (Stage 1).
"""

import pytest
from src.ner import find_matching_words_with_cosine_similarity, find_matching_words_with_cosine_similarity_cpu

def test_exact_text_match():
    """Test that exact substring match finds dictionary terms in chunk."""
    # Dictionary with terms that appear in text
    vocab = {
        "bonded": {"en": "bonded"},
        "hooder": {"en": "hooder"},
        "crushed": {"en": "crushed"}
    }
    
    # Chunk text containing these terms
    text = "The bonded soldier crushed the enemy's weapon. His hooder glowed."
    
    # Expected: all three terms should be matched
    matched = find_matching_words_with_cosine_similarity(text, vocab, "en", threshold=0.8)
    
    # MUST find exact matches regardless of cosine similarity
    assert "bonded" in matched
    assert "crushed" in matched
    assert "hooder" in matched

def test_exact_text_match_cpu():
    """Test CPU version for exact substring match."""
    vocab = {
        "bonded": {"en": "bonded"},
        "hooder": {"en": "hooder"}
    }
    
    text = "The bonded soldier with his hooder weapon."
    
    matched = find_matching_words_with_cosine_similarity_cpu(text, vocab, "en", threshold=0.8)
    
    assert "bonded" in matched
    assert "hooder" in matched

def test_multi_word_term_match():
    """Test exact match for multi-word terms like 'John Smith'."""
    vocab = {
        "john_smith": {"en": "John Smith"},
        "mad_hatter": {"en": "Mad Hatter"}
    }
    
    text = "John Smith met the Mad Hatter at the party."
    
    matched = find_matching_words_with_cosine_similarity(text, vocab, "en", threshold=0.8)
    
    # Multi-word terms should be matched as substrings
    assert "John Smith" in matched
    assert "Mad Hatter" in matched

def test_no_match_for_missing_terms():
    """Test that terms NOT in text are not matched."""
    vocab = {
        "alice": {"en": "Alice"},
        "wonderland": {"en": "Wonderland"},
        "rabbit": {"en": "Rabbit"}
    }
    
    text = "Alice went to a strange place. No rabbits here."
    
    matched = find_matching_words_with_cosine_similarity(text, vocab, "en", threshold=0.8)
    
    # Alice is in text -> match
    assert "Alice" in matched
    # Wonderland NOT in text -> no match
    assert "Wonderland" not in matched
    # Rabbit NOT in text (only "rabbits" with 's') -> no match unless semantic
    # This is edge case: exact match should NOT find "rabbit" in "rabbits"
    assert "Rabbit" not in matched  # Exact match, not semantic
```

- [ ] **Step 2: Run test to verify it fails**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_exact_text_match -v
```
Expected: FAIL (text search not implemented yet)

---

### Task 1: Implement Stage 1: Exact Text Search in ner.py (GPU version)

**Files:**
- Modify: `src/ner.py:415-462` (find_matching_words_with_cosine_similarity)

**Goal:** Add exact substring match before cosine similarity.

- [ ] **Step 1: Write test (already done in Task 0)**

- [ ] **Step 2: Implement Stage 1 text search**
```python
def find_matching_words_with_cosine_similarity(text, vocab, lng, threshold=0.8, batch_size=1024):
    """
    Two-stage matching:
    1. TEXT SEARCH: Exact substring match (priority)
    2. COSINE SEARCH: Semantic similarity for unmatched terms
    
    Returns:
        List of matched vocabulary terms
    """
    if config.debug:
        print("Starting vocabulary matching (GPU): Stage 1 - Text Search")
    
    if not text or not vocab:
        return []
    
    matched_words_set = set()
    
    # STAGE 1: TEXT SEARCH (exact match)
    # ==================================
    text_lower = text.lower()
    
    for entry_key, entry in vocab.items():
        source_term = entry.get(lng, "")
        if not source_term:
            continue
        
        # Exact substring check (case-insensitive)
        if source_term.lower() in text_lower:
            matched_words_set.add(source_term)
            if config.debug:
                print(f"  Text match: '{source_term}' found in chunk")
    
    # STAGE 2: COSINE SEARCH (semantic)
    # =================================
    # Filter vocab: only terms NOT already matched by text search
    unmatched_vocab = {
        k: v for k, v in vocab.items() 
        if v.get(lng, "") not in matched_words_set
    }
    
    if not unmatched_vocab:
        if config.debug:
            print(f"All terms matched by text search: {len(matched_words_set)}")
        return list(matched_words_set)
    
    # Use LOWER threshold for semantic matching
    semantic_threshold = 0.6  # Lower threshold for semantic matches
    
    try:
        spacy.prefer_gpu()
        nlp = load_spacy_model(config.nermodel)
        nlp.max_length = 110000
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"SpaCy error: {e}")
        return list(matched_words_set)
    
    # Build vectors for unmatched terms
    orig_values = [entry[lng] for entry in unmatched_vocab.values() if lng in entry]
    
    valid_vocab_words = []
    vocab_vectors = []
    
    for phrase in orig_values:
        sub_words = phrase.split()
        sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
        sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]
        
        if sub_vecs:
            mean_vec = np.mean(np.vstack(sub_vecs), axis=0)
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)
    
    if not vocab_vectors:
        return list(matched_words_set)
    
    # GPU cosine similarity
    vocab_matrix = cp.asarray(np.vstack(vocab_vectors))
    vocab_matrix = vocab_matrix / cp.linalg.norm(vocab_matrix, axis=1, keepdims=True)
    
    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i+batch_size]
        token_vectors = np.vstack([t.vector for t in batch_tokens])
        token_vectors = cp.asarray(token_vectors)
        token_vectors = token_vectors / cp.linalg.norm(token_vectors, axis=1, keepdims=True)
        
        sims = cp.dot(token_vectors, vocab_matrix.T)
        
        best_matches = cp.where(sims > semantic_threshold)
        for _, vi in zip(*best_matches):
            matched_words_set.add(valid_vocab_words[int(vi)])
    
    if config.debug:
        text_matches = len([w for w in matched_words_set if w.lower() in text_lower])
        semantic_matches = len(matched_words_set) - text_matches
        print(f"  Total matches: {len(matched_words_set)} (text: {text_matches}, semantic: {semantic_matches})")
    
    return list(matched_words_set)
```

- [ ] **Step 3: Run test to verify it passes**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_exact_text_match -v
```
Expected: PASS

---

### Task 2: Implement Stage 1: Exact Text Search in ner.py (CPU version)

**Files:**
- Modify: `src/ner.py:482-540` (find_matching_words_with_cosine_similarity_cpu)

**Goal:** Same two-stage logic for CPU fallback.

- [ ] **Step 1: Test already written (Task 0)**

- [ ] **Step 2: Implement CPU version**
```python
def find_matching_words_with_cosine_similarity_cpu(text, vocab, lng, threshold=0.8, batch_size=256):
    """
    Two-stage matching (CPU version):
    1. TEXT SEARCH: Exact substring match
    2. COSINE SEARCH: Semantic similarity (NumPy)
    """
    if config.debug:
        print("Starting vocabulary matching (CPU): Stage 1 - Text Search")
    
    if not text or not vocab:
        return []
    
    matched_words_set = set()
    
    # STAGE 1: TEXT SEARCH (exact match)
    # ==================================
    text_lower = text.lower()
    
    for entry_key, entry in vocab.items():
        source_term = entry.get(lng, "")
        if not source_term:
            continue
        
        if source_term.lower() in text_lower:
            matched_words_set.add(source_term)
            if config.debug:
                print(f"  Text match: '{source_term}' found in chunk")
    
    # STAGE 2: COSINE SEARCH (semantic)
    # =================================
    unmatched_vocab = {
        k: v for k, v in vocab.items() 
        if v.get(lng, "") not in matched_words_set
    }
    
    if not unmatched_vocab:
        return list(matched_words_set)
    
    semantic_threshold = 0.6
    
    try:
        nlp = load_spacy_model(config.nermodel)
        nlp.max_length = 110000
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"SpaCy error: {e}")
        return list(matched_words_set)
    
    orig_values = [entry[lng] for entry in unmatched_vocab.values() if lng in entry]
    
    valid_vocab_words = []
    vocab_vectors = []
    
    for phrase in orig_values:
        sub_words = phrase.split()
        sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
        sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]
        
        if sub_vecs:
            mean_vec = np.mean(np.vstack(sub_vecs), axis=0)
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)
    
    if not vocab_vectors:
        return list(matched_words_set)
    
    # CPU cosine similarity (NumPy)
    vocab_matrix = np.vstack(vocab_vectors)
    vocab_matrix = vocab_matrix / np.linalg.norm(vocab_matrix, axis=1, keepdims=True)
    
    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i+batch_size]
        token_vectors = np.vstack([t.vector for t in batch_tokens])
        token_vectors = token_vectors / np.linalg.norm(token_vectors, axis=1, keepdims=True)
        
        sims = np.dot(token_vectors, vocab_matrix.T)
        
        best_matches = np.where(sims > semantic_threshold)
        for _, vi in zip(*best_matches):
            matched_words_set.add(valid_vocab_words[vi])
    
    if config.debug:
        text_matches = len([w for w in matched_words_set if w.lower() in text_lower])
        semantic_matches = len(matched_words_set) - text_matches
        print(f"  Total: {len(matched_words_set)} (text: {text_matches}, semantic: {semantic_matches})")
    
    return list(matched_words_set)
```

- [ ] **Step 3: Run test**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_exact_text_match_cpu -v
```
Expected: PASS

---

### Task 3: Write test for formatting without trailing commas

**Files:**
- Modify: `tests/test_vocab_matching.py`

**Goal:** Test that formatting removes trailing empty commas.

- [ ] **Step 1: Add test for formatting**
```python
def test_format_standard_no_trailing_commas():
    """Test that format_standard removes trailing empty commas."""
    from src.vocabulary_manager import VocabEntry, VocabularyManager
    
    # Entries with empty fields
    entries = [
        VocabEntry(source="bonded", target="связанный", category="", gender="", notes=""),
        VocabEntry(source="hooder", target="капюшонник", category="PERSON", gender="он", notes="инопланетное существо"),
        VocabEntry(source="crushed", target="раздавил", category="", gender="", notes=""),
    ]
    
    # Mock vocab manager (no file needed)
    manager = VocabularyManager.__new__(VocabularyManager)
    
    formatted = manager._format_standard(entries)
    
    lines = formatted.split('\n')
    
    # No trailing commas for entries without metadata
    assert lines[0] == "bonded = связанный"  # NOT "bonded = связанный,, ,"
    # Full metadata for entries with data
    assert lines[1] == "hooder = капюшонник, PERSON, он, инопланетное существо"
    assert lines[2] == "crushed = раздавил"

def test_format_hunyuan_no_trailing_commas():
    """Test Hunyuan format."""
    from src.vocabulary_manager import VocabEntry, VocabularyManager
    
    entries = [
        VocabEntry(source="bonded", target="связанный", category="", gender="", notes=""),
        VocabEntry(source="Alice", target="Алиса", category="PERSON", gender="", notes=""),
    ]
    
    manager = VocabularyManager.__new__(VocabularyManager)
    formatted = manager._format_hunyuan(entries)
    
    # Format: source=target(category) if category exists
    assert "bonded=связанный" in formatted  # No category
    assert "Alice=Алиса(PERSON)" in formatted  # With category
```

- [ ] **Step 2: Run test (should fail)**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_format_standard_no_trailing_commas -v
```
Expected: FAIL (trailing commas present)

---

### Task 4: Fix formatting in vocabulary_manager.py

**Files:**
- Modify: `src/vocabulary_manager.py:780-820` (_format_standard, _format_hunyuan, _format_gemma)

**Goal:** Remove trailing empty commas.

- [ ] **Step 1: Fix _format_standard**
```python
def _format_standard(self, entries: List[VocabEntry]) -> str:
    """
    Standard format: source = target
    Metadata added ONLY if fields have content (no trailing commas).
    """
    if not entries:
        return ""
    
    lines = []
    for entry in entries:
        line = f"{entry.source} = {entry.target}"
        
        # Collect non-empty metadata only
        meta_parts = []
        if entry.category:
            meta_parts.append(entry.category)
        if entry.gender:
            meta_parts.append(entry.gender)
        if entry.notes:
            meta_parts.append(entry.notes)
        
        # Add metadata ONLY if we have non-empty parts
        if meta_parts:
            line += ", " + ", ".join(meta_parts)
        
        lines.append(line)
    
    return "\n".join(lines)
```

- [ ] **Step 2: Run test**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_format_standard_no_trailing_commas -v
```
Expected: PASS

---

### Task 5: Remove fallback to full vocabulary in app.py

**Files:**
- Modify: `app.py:79-95` (get_formatted_vocab_for_chunk)

**Goal:** Remove fallback that injects entire vocabulary.

- [ ] **Step 1: Write test for no fallback**
```python
def test_no_full_vocab_fallback():
    """Test that empty vocab doesn't fall back to full vocabulary."""
    from unittest.mock import MagicMock, patch
    from app import TranslationEngine
    
    # Mock vocab_manager with empty result
    mock_manager = MagicMock()
    mock_manager.vocab = {"alice": MagicMock(), "wonderland": MagicMock()}
    mock_manager.get_vocab_for_chunk.return_value = []  # Empty
    mock_manager.format_for_model.return_value = ""
    
    engine = TranslationEngine.__new__(TranslationEngine)
    engine.vocab_manager = mock_manager
    
    # Chunk with no matching terms
    result = engine.get_formatted_vocab_for_chunk("Some random text here", 0, 0)
    
    # Should return empty string, NOT full vocabulary
    assert result == ""
    
    # format_for_model should NOT be called with full vocab
    mock_manager.format_for_model.assert_called_once_with([], "model_name")
```

- [ ] **Step 2: Remove fallback in app.py**
```python
def get_formatted_vocab_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> str:
    """
    Get formatted vocabulary for chunk.
    
    Returns empty string if no matching terms (no fallback to full vocab).
    """
    if not self.vocab_manager:
        logger.warning("vocab_manager not initialized")
        return ""
    
    entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
    
    if not entries:
        # Empty vocab is valid for chunks without dictionary terms
        logger.info(f"Chunk {s_idx}-{c_idx}: No matching vocabulary terms")
        return ""
    
    formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
    
    if config.debug:
        logger.debug(f"Vocab for chunk {s_idx}-{c_idx}: {len(entries)} terms")
    elif len(entries) > 0:
        logger.info(f"Vocabulary: {len(entries)} terms for chunk {s_idx}-{c_idx}")
    
    return formatted
```

- [ ] **Step 3: Run test**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py::test_no_full_vocab_fallback -v
```
Expected: PASS

---

### Task 6: Run full test suite and verify fixes

**Files:**
- All test files

**Goal:** Verify all tests pass after fixes.

- [ ] **Step 1: Run all vocab matching tests**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_vocab_matching.py -v
```
Expected: All PASS

- [ ] **Step 2: Run existing series vocab tests (ensure no regression)**
```bash
cd ~/prj/sunny-narrator && pytest tests/test_series_vocab.py tests/test_series_vocab_robust.py -v
```
Expected: All PASS (or skip if LLM required)

- [ ] **Step 3: Manual verification with test dictionary**
```bash
cd ~/prj/sunny-narrator
# Create test dictionary
cat > books/test_chunk.dic << 'EOF'
# Vocabulary test
bonded = связанный
hooder = капюшонник, PERSON, он, инопланетное существо
crushed = раздавил
EOF

# Test matching logic manually
python -c "
from src.ner import find_matching_words_with_cosine_similarity
vocab = {'bonded': {'en': 'bonded'}, 'hooder': {'en': 'hooder'}, 'crushed': {'en': 'crushed'}}
text = 'The bonded soldier crushed the weapon. His hooder glowed.'
matched = find_matching_words_with_cosine_similarity(text, vocab, 'en')
print('Matched:', matched)
assert 'bonded' in matched and 'crushed' in matched and 'hooder' in matched
print('✅ All terms matched correctly')
"
```

- [ ] **Step 4: Commit changes**
```bash
cd ~/prj/sunny-narrator
git add tests/test_vocab_matching.py src/ner.py src/vocabulary_manager.py app.py
git commit -m "fix(vocab): Add exact text search before cosine similarity, remove trailing commas"
```

---

## Summary

**Total tasks:** 7  
**Estimated time:** 35-45 minutes  
**Priority:** HIGH (critical bug fix)

**Dependencies:**
- Task 0 → Task 1, Task 2 (test first)
- Task 3 → Task 4 (test first)
- Task 5 independent
- Task 6 depends on all previous

---

**Next step:** Execute this plan with `subagent-driven-development` or `executing-plans` skill.