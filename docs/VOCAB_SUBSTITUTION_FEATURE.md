# Vocabulary Auto-Substitution Feature

## Overview

This feature automatically replaces dictionary words in `source_text` BEFORE Stage 1 (INITIAL) translation to ensure the LLM sees and uses translated terms from the vocabulary.

## How It Works

1. **Word Boundary Matching**: Only exact word matches are replaced (uses `\bword\b` regex pattern)
2. **Stage 1 Only**: Substitution happens ONLY in `TranslationPipeline.initial_translation()`
3. **Preserve Original**: Stages 2-4 (reflection, improve, final_edit) see the ORIGINAL `source_text` without substitutions
4. **Exact Matches Only**: Only dictionary entries with exact word matches are replaced (no inflection handling)

## Example

**Input:**
```
source_text: "everytime dragon fly beautiful dragon"
vocab_dict: {"dragon": "драккар", "fly": "летать"}
```

**Stage 1 sees:**
```
"everytime драккар летать beautiful драккар"
```

**Stages 2-4 see:**
```
"everytime dragon fly beautiful dragon"  # ORIGINAL, no substitutions
```

## Implementation

### Location
- Function: `replace_vocab_in_text()` in `src/utils.py`
- Call site: `TranslationPipeline.initial_translation()` at the start

### Algorithm
```python
def replace_vocab_in_text(source_text: str, vocab_dict: Dict[str, str], source_lang: str) -> str:
    if not vocab_dict or not source_text:
        return source_text
    
    # Sort by length desc to replace longer matches first
    sorted_keys = sorted(vocab_dict.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in sorted_keys]
    pattern = r'\b(' + '|'.join(escaped_keys) + r')\b'
    
    def replace_func(match):
        word = match.group(1)
        return vocab_dict.get(word, word)
    
    return re.sub(pattern, replace_func, source_text)
```

### Integration
```python
@log_entry
def initial_translation(self, context: TranslationContext) -> TranslationResult:
    # Replace dictionary words in source_text BEFORE translation
    if context.vocab_dict:
        context = dataclasses.replace(
            context,
            source_text=replace_vocab_in_text(
                context.source_text,
                context.vocab_dict,
                context.source_lang
            )
        )
    
    # ... rest of existing code (unchanged)
```

## Benefits

1. **Higher Dictionary Value**: LLM always uses translated terms from dictionary
2. **Better Quality Verification**: Reflection stages see original text to verify translation quality
3. **Exact Control**: Only exact dictionary matches are replaced

## Limitations

1. **No Inflection Handling**: `dragon` → `драккар`, but `dragons` → NOT replaced
2. **Stage 1 Only**: Only initial translation uses substitutions
3. **Word Boundaries Only**: Substrings like `dragonfly` are NOT replaced
