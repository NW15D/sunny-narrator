# NER Guide — Named Entity Recognition for Vocabulary Matching

## 📋 Overview

Sunny Narrator uses **Named Entity Recognition (NER)** to automatically identify and match vocabulary terms in each chunk before translation.

## 🎯 How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Load vocabulary from .dic file                               │
│    └─ Dictionary with source=target terms                       │
│                                                                 │
│ 2. For each chunk:                                              │
│    ├─ Extract text from chunk                                   │
│    ├─ Run NER matching (GPU or CPU)                             │
│    ├─ Find vocabulary terms using cosine similarity             │
│    └─ Cache results for this chunk                              │
│                                                                 │
│ 3. Format matched terms for model                               │
│    ├─ Hunyuan:  Alice=Алиса(PERSON)                             │
│    ├─ Gemma:    Alice → Алиса                                   │
│    └─ Standard: Alice = Алиса (PERSON) [she]                    │
│                                                                 │
│ 4. Inject into translation prompt                               │
│    └─ <vocabulary>{formatted_vocab}</vocabulary>                │
└─────────────────────────────────────────────────────────────────┘
```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Enable/disable NER
NER=true                    # true=enabled, false=disabled

# spaCy model for NER
NERMODEL=en_core_web_lg     # Large model with vectors (required)

# Model selection by language
# English:  en_core_web_lg
# Russian:  ru_core_news_lg
# German:   de_core_news_lg
# French:   fr_core_news_lg
# Spanish:  es_core_news_lg
```

### GPU vs CPU Mode

**Automatic detection** — system selects best available mode:

| Mode | Speed | Requirements | Function |
|------|-------|--------------|----------|
| **GPU** | Fast (10-50x) | CUDA, cupy | `find_matching_words_with_cosine_similarity()` |
| **CPU** | Slower | NumPy only | `find_matching_words_with_cosine_similarity_cpu()` |

**No configuration needed** — automatically detected at runtime.

## 🔧 Installation

### With GPU Support

```bash
# Install spaCy with CUDA support
pip install spacy[cuda11x]

# Download large model with vectors
python -m spacy download en_core_web_lg

# Verify GPU is available
python -c "import torch; print(torch.cuda.is_available())"
```

### CPU-Only

```bash
# Install spaCy (CPU version)
pip install spacy

# Download large model with vectors
python -m spacy download en_core_web_lg

# Verify installation
python -c "import spacy; nlp = spacy.load('en_core_web_lg'); print('OK')"
```

## 📊 NER Workflow

### 1. Dictionary Initialization

```python
from src.vocabulary_manager import VocabularyManager

manager = VocabularyManager(book_path="books/MyBook.fb2")
vocab = manager.initialize()

# If .dic file exists: loads from file
# If .dic missing: creates from NER (requires user approval)
```

### 2. Per-Chunk Vocabulary Matching

```python
# For each chunk, get relevant vocabulary
entries = manager.get_vocab_for_chunk(chunk_text, s_idx=0, c_idx=0)

# Returns: List[VocabEntry] with matched terms
# Example: [VocabEntry('Alice', 'Алиса', 'PERSON', 'she'), ...]
```

### 3. Format for Model

```python
# Format matched terms for specific model
formatted = manager.format_for_model(entries, model="Hunyuan")

# Output: "Alice=Алиса(PERSON) | Wonderland=Страна Чудес(LOC)"
```

### 4. Inject into Prompt

```python
# Prompt template uses {vocab_dict} placeholder
# Automatically replaced with formatted vocabulary
```

## 🧠 Cosine Similarity Matching

### How It Works

1. **Tokenize** chunk text into words
2. **Generate vectors** using spaCy word embeddings
3. **Compare** with vocabulary term vectors
4. **Match** if cosine similarity > threshold (0.8)

### Example

```python
# Chunk text: "Alice went to Wonderland and met the Queen"
# Vocabulary: {
#   "alice": {"english": "Alice", "russian": "Алиса"},
#   "wonderland": {"english": "Wonderland", "russian": "Страна Чудес"},
#   "queen": {"english": "Queen", "russian": "Королева"}
# }

# Matching process:
# 1. Tokenize: ["Alice", "went", "to", "Wonderland", "and", "met", "the", "Queen"]
# 2. Generate vectors for each token
# 3. Compare with vocabulary vectors:
#    - "Alice" vs "Alice" → similarity=0.98 ✓ MATCH
#    - "Wonderland" vs "Wonderland" → similarity=0.95 ✓ MATCH
#    - "Queen" vs "Queen" → similarity=0.92 ✓ MATCH
# 4. Return matched terms: ["Alice", "Wonderland", "Queen"]
```

### Threshold Tuning

```bash
# Default threshold: 0.8
# Higher = more precise, fewer matches
# Lower = more matches, possible false positives

# Adjust in src/ner.py if needed:
threshold=0.85  # More strict
threshold=0.75  # More lenient
```

## 📈 Performance

### GPU Mode (Recommended)

| Chunk Size | Time | Speed |
|------------|------|-------|
| 1000 chars | 10ms | Fast |
| 5000 chars | 50ms | Fast |
| 10000 chars | 100ms | Fast |

### CPU Mode (Fallback)

| Chunk Size | Time | Speed |
|------------|------|-------|
| 1000 chars | 100ms | OK |
| 5000 chars | 500ms | OK |
| 10000 chars | 1000ms | Slow |

**Recommendation:** Use GPU for large books (>100k chars).

## 🐛 Troubleshooting

### Issue: NER Not Working

**Symptoms:**
- No vocabulary terms matched
- `get_vocab_for_chunk()` returns empty list

**Check:**
```bash
# 1. Is NER enabled?
grep NER .env
# Should be: NER=true

# 2. Is spaCy model installed?
python -m spacy validate

# 3. Does model have vectors?
python -c "import spacy; nlp = spacy.load('en_core_web_lg'); print(nlp('test').has_vector)"
# Should be: True
```

**Solution:**
```bash
# Install model with vectors
python -m spacy download en_core_web_lg
```

### Issue: GPU Not Detected

**Symptoms:**
- Logs show "CPU mode" instead of "GPU mode"
- Slow vocabulary matching

**Check:**
```bash
# 1. Is CUDA available?
python -c "import torch; print(torch.cuda.is_available())"

# 2. Is cupy installed?
python -c "import cupy; print(cupy.__version__)"
```

**Solution:**
```bash
# Install cupy for CUDA
pip install cupy-cuda11x  # For CUDA 11.x
pip install cupy-cuda12x  # For CUDA 12.x
```

### Issue: Too Many/Few Matches

**Symptoms:**
- Vocabulary includes irrelevant terms
- Important terms not matched

**Solution:**
```python
# Adjust threshold in src/ner.py
# Default: threshold=0.8

# More strict (fewer matches)
threshold=0.85

# More lenient (more matches)
threshold=0.75
```

## 📝 API Reference

### ner.py Functions

#### `find_matching_words_with_cosine_similarity()`

GPU-accelerated vocabulary matching.

```python
from src import ner as ner_module

matched = ner_module.find_matching_words_with_cosine_similarity(
    text=chunk_text,
    vocab=vocab_dict,
    lng="english",
    threshold=0.8,
    batch_size=1024
)
```

#### `find_matching_words_with_cosine_similarity_cpu()`

CPU-only vocabulary matching (fallback).

```python
matched = ner_module.find_matching_words_with_cosine_similarity_cpu(
    text=chunk_text,
    vocab=vocab_dict,
    lng="english",
    threshold=0.8,
    batch_size=256  # Smaller batch for CPU
)
```

### vocabulary_manager.py Methods

#### `get_vocab_for_chunk()`

Get vocabulary entries for a chunk (auto-selects GPU/CPU).

```python
entries = manager.get_vocab_for_chunk(
    chunk_text=chunk,
    s_idx=0,
    c_idx=0
)
```

#### `format_for_model()`

Format vocabulary for specific model.

```python
formatted = manager.format_for_model(
    entries=entries,
    model="Hunyuan"  # or "Gemma", "Mistral", etc.
)
```

## 📊 Statistics & Monitoring

### Enable Debug Logging

```bash
DEBUG=on
```

### Output Example

```
DEBUG: Chunk 0-0 (GPU): 5 vocab terms matched
DEBUG: Chunk 0-1 (GPU): 3 vocab terms matched
DEBUG: Chunk 0-2 (CPU): 4 vocab terms matched  # GPU unavailable
```

### Metrics to Track

```python
ner_stats = {
    'total_chunks': 100,
    'chunks_with_vocab': 75,
    'total_matches': 350,
    'avg_matches_per_chunk': 3.5,
    'gpu_mode': True,
    'avg_match_time_ms': 50
}
```

## 🎯 Best Practices

### 1. Always Use Large spaCy Models

```bash
# Good (has vectors)
en_core_web_lg
ru_core_news_lg
de_core_news_lg

# Bad (no vectors)
en_core_web_sm
en_core_web_md
```

### 2. Keep Vocabulary Focused

```dic
# Good (specific terms)
Alice = Алиса | PERSON | she
Wonderland = Страна Чудес | LOC

# Bad (common words)
the = the | |
and = и | |
```

### 3. Monitor Match Quality

```bash
# Check if matched terms are relevant
grep "vocab terms matched" logs/*.log

# If too many false positives:
# - Increase threshold to 0.85
# - Clean up dictionary
```

### 4. Cache is Your Friend

```python
# Vocabulary matching is cached per chunk
# No need to re-match same chunk
# Cache key: (s_idx, c_idx)
```

## 📝 Changelog

- **2026-03-29:** Added CPU fallback mode (`find_matching_words_with_cosine_similarity_cpu()`)
- **2026-03-29:** Automatic GPU/CPU detection in `get_vocab_for_chunk()`
- **Previous:** Initial NER implementation with GPU support
