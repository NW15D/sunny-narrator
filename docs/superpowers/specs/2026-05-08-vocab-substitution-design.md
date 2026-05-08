# Vocabulary Auto-Substitution Design Document

**Goal:** Automatically replace dictionary words in source_text BEFORE Stage 1 (INITIAL) translation to ensure LLM uses translated terms from vocabulary. Stages 2-4 should see original source_text to verify translation quality.

**Architecture:** 
- Add `replace_vocab_in_text()` function in `src/utils.py`
- Call substitution at start of `TranslationPipeline.initial_translation()`
- Preserve original source_text for reflection/improve stages

**Components:**
- `replace_vocab_in_text()` - Regex-based word boundary matching with dictionary substitution
- `TranslationPipeline.initial_translation()` - Calls substitution before LLM translation call
- `TranslationContext` - Immutable context passed through pipeline stages

**Data Flow:**
```
source_text "everytime dragon fly" + vocab {"dragon":"драккар"}
    ↓
replace_vocab_in_text() → source_text "everytime драккар fly"
    ↓
Stage 1 (INITIAL): LLM translates substituted text
    ↓
Stage 2 (REFLECTION): See ORIGINAL source_text "everytime dragon fly"
Stage 3 (IMPROVE): See ORIGINAL source_text "everytime dragon fly"  
Stage 4 (FINAL_EDIT): See ORIGINAL source_text "everytime dragon fly"
```

**Testing Strategy:**
- Unit tests for `replace_vocab_in_text()` with word boundary cases
- Integration test verifying Stage 1 sees substituted, Stages 2-4 see original
- Edge cases: empty vocab, empty text, special regex characters
