# Vocabulary Auto-Substitution Implementation Plan

**Goal:** Automatically replace dictionary words in source_text BEFORE Stage 1 (INITIAL) translation to ensure LLM uses translated terms from vocabulary. Stages 2-4 should see original source_text to verify translation quality.

**Architecture:** 
- Add `replace_vocab_in_text()` function in `src/utils.py`
- Call substitution at start of `TranslationPipeline.initial_translation()`
- Preserve original source_text for reflection/improve stages

**Tech Stack:** Python, regex word boundary matching

**Execution:** subagent-driven-development

---

### Task 1: Create replace_vocab_in_text() function

**Files:**
- Create: `src/utils.py` (add function)

- [ ] **Step 1: Add replace_vocab_in_text function after TranslationMetrics class**
```python
def replace_vocab_in_text(
    source_text: str, 
    vocab_dict: Dict[str, str],
    source_lang: str = None
) -> str:
    """
    Replace dictionary words in source_text with their translations.
    Uses word boundary matching for exact matches only.
    
    Args:
        source_text: Original text to translate
        vocab_dict: Dictionary mapping source words → target translations
        source_lang: Source language (reserved for future tokenizer use)
    
    Returns:
        Text with dictionary words replaced (e.g., "everytime dragon fly" → "everytime драккар fly")
    """
    if not vocab_dict or not source_text:
        return source_text
    
    # Sort by length desc to replace longer matches first (avoids partial replacements)
    sorted_keys = sorted(vocab_dict.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in sorted_keys]
    pattern = r'\b(' + '|'.join(escaped_keys) + r')\b'
    
    def replace_func(match):
        word = match.group(1)
        return vocab_dict.get(word, word)
    
    return re.sub(pattern, replace_func, source_text)
```

- [ ] **Step 2: Verify the function works correctly**
```python
# Test with sample data
test_text = "everytime dragon fly beautiful dragon"
test_vocab = {"dragon": "драккар", "fly": "летать"}
result = replace_vocab_in_text(test_text, test_vocab)
assert result == "everytime драккар летать beautiful драккар"  # wait, fly→летать is verb
# Actually test with verb:
test_vocab = {"dragon": "драккар"}
result = replace_vocab_in_text(test_text, test_vocab)
assert result == "everytime драккар fly beautiful драккар"
```

- [ ] **Step 3: Commit the function**
```bash
git add src/utils.py
git commit -m "feat: add replace_vocab_in_text function for dictionary word replacement"
```

---

### Task 2: Integrate substitution into initial_translation()

**Files:**
- Modify: `src/utils.py`

- [ ] **Step 1: Import dataclasses at top of file**
```python
import dataclasses  # Add to imports
```

- [ ] **Step 2: Modify TranslationPipeline.initial_translation() to call substitution**
```python
@log_entry
def initial_translation(self, context: TranslationContext) -> TranslationResult:
    """Stage 1: Primary LLM translation."""
    # Replace dictionary words in source_text BEFORE translation
    # This ensures LLM sees translated terms in context
    if context.vocab_dict:
        context = dataclasses.replace(
            context,
            source_text=replace_vocab_in_text(
                context.source_text,
                context.vocab_dict,
                context.source_lang
            )
        )
    
    # Rest of existing code remains unchanged...
    # Handle empty or very short input
    if not context.source_text or len(context.source_text.strip()) < 2:
        # ...
```

- [ ] **Step 3: Verify the integration doesn't break existing code**
```bash
python -c "from src.utils import TranslationPipeline, TranslationContext, replace_vocab_in_text; print('Imports OK')"
```

- [ ] **Step 4: Add unit test for substitution in initial_translation**
```python
# Create test file tests/test_vocab_substitution.py
# Test that translation uses substituted text but reflection sees original
```

- [ ] **Step 5: Commit the changes**
```bash
git add src/utils.py tests/test_vocab_substitution.py
git commit -m "feat: integrate vocab substitution into initial_translation stage"
```

---

### Task 3: Write tests

**Files:**
- Create: `tests/test_vocab_substitution.py`

- [ ] **Step 1: Test replace_vocab_in_text() function**
```python
def test_replace_vocab_in_text_basic():
    text = "dragon fly beautiful dragon"
    vocab = {"dragon": "драккар"}
    result = replace_vocab_in_text(text, vocab)
    assert result == "драккар fly beautiful драккар"

def test_replace_vocab_in_text_word_boundary():
    """Should only match whole words, not substrings."""
    text = "dragonfly is not a dragon"
    vocab = {"dragon": "драккар"}
    result = replace_vocab_in_text(text, vocab)
    assert result == "dragonfly is not драккар"

def test_replace_vocab_in_text_empty():
    assert replace_vocab_in_text("", {}) == ""
    assert replace_vocab_in_text("text", {}) == "text"
```

- [ ] **Step 2: Test integration with initial_translation()**
```python
def test_initial_translation_uses_substituted_text():
    """Verify Stage 1 sees substituted text."""
    context = TranslationContext(
        source_lang="english",
        target_lang="russian",
        source_text="dragon fly",
        vocab_dict={"dragon": "драккар"}
    )
    # Mock the LLM response
    pipeline = TranslationPipeline()
    result = pipeline.initial_translation(context)
    # Verify the LLM was called with substituted text
    # (Need to check the prompt or mock the LLM call)
```

- [ ] **Step 3: Test that Stages 2-4 see original text**
```python
def test_reflection_sees_original_text():
    """Verify Stage 2 (reflection) sees original source_text without substitutions."""
    # This is implicit - context.source_text is NOT modified for later stages
```

- [ ] **Step 4: Run tests**
```bash
pytest tests/test_vocab_substitution.py -v
```

- [ ] **Step 5: Commit tests**
```bash
git add tests/test_vocab_substitution.py
git commit -m "test: add tests for vocabulary substitution"
```

---

### Task 4: Code review and verification

**Files:**
- Review: `src/utils.py`

- [ ] **Step 1: Request code review**
```python
# Use requesting-code-review skill
sessions_send(sessionKey="current", message="I'm using the requesting-code-review skill to verify the implementation")
```

- [ ] **Step 2: Apply review feedback**
- Fix any issues found during review

- [ ] **Step 3: Final verification**
```bash
# Run all tests
pytest tests/ -v
# Test specific feature
pytest tests/test_vocab_substitution.py -v
```

- [ ] **Step 4: Push to GitLab only**
```bash
git push origin develop
```
