# NER Guide — Named Entity Recognition for Vocabulary Matching

## 📋 Overview

Sunny Narrator uses **Named Entity Recognition (NER)** to automatically identify and match vocabulary terms in each chunk before translation.

Languages verified on real spaCy models (NER, term forms, article/particle
cleanup) and their limits: [LANGUAGES.md](LANGUAGES.md).

## 🎯 How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Load vocabulary from .dic file                               │
│    └─ Dictionary with source=target terms                       │
│                                                                 │
│ 2. For each chunk:                                              │
│    ├─ Extract text from chunk                                   │
│    ├─ Lexical match: word forms / lemmas, substring for CJK     │
│    ├─ Cosine similarity for the remaining terms (GPU or CPU)    │
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

# DICTIONARY: use an explicit .dic file instead of the automatic
# <book_name>.dic lookup next to the source file. Empty = auto lookup.
# Also settable per run via --dictionary <path> (CLI wins over .env).
DICTIONARY=
```

### Explicit dictionary path (`DICTIONARY` / `--dictionary`)

By default the vocabulary file is found automatically next to the source
book: `books/MyBook.fb2` → `books/MyBook.dic` (see step 1 in the workflow
above). Setting `DICTIONARY=/path/to/some.dic` in `.env`, or passing
`--dictionary /path/to/some.dic` on the command line, overrides that lookup
and uses the given file instead — for both the classic (FB2/TXT) and the
Calibre (DOCX/EPUB/PDF) pipeline. The CLI flag takes precedence over the
`.env` value. This is useful for reusing a shared/series dictionary
(built with `--build-series-dict`) or for keeping the `.dic` outside the
book's own folder. If the file does not exist yet, both pipelines build it
at that path, exactly as they would at the default `<book_name>.dic`
location, and both pipelines stop after creating it so you can review it. The directory of the
given path must already exist, otherwise `app.py` exits with an error.

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

## 🔤 Lexical Matching (stage 1)

The same matcher runs for every input format — FB2/TXT (classic pipeline)
and EPUB/DOCX/PDF (Calibre pipeline) both go through
`VocabularyManager.get_vocab_for_chunk()`. Stage 1 is `lexicon.find_terms()` / `resolve_terms()`:

- Words are split by Unicode category (letters/marks/digits), not by regex,
  so it works for any script. A multi-word term must match consecutive words.
- **Priority** (`lexicon.term_rank`): a term of more words beats the shorter
  terms it contains (`Mad Hatter` over `Hatter`), then the longer one, then
  the leftmost. Words are counted as the matcher splits them, so
  `Jean-Luc-Marie` is three words. A term whose every occurrence is covered
  this way is dropped from the chunk (`lexicon.resolve_terms` also reports it
  as *shadowed*, so the cosine stage does not bring it back), and the prompt
  lists entries in priority order.
- **Case:** only an occurrence in the term's capitalisation (inflection
  allowed: `Mad Hatters`) or in ALL CAPS shadows other terms. In "the mad
  Hatter" both `Mad Hatter` and `Hatter` stay in the prompt and `Hatter` is
  substituted. A lowercase term (`spidergun`) fits any case.
- **Markup is not text** (`lexicon.non_text_spans`): FB2/HTML tags, markdown
  link and image targets, reference definitions, attribute blocks
  (`{#id .class}`) and URLs never match, and no term spans across them, so
  `Mad</p><p>Hatter` (two paragraphs) and `Mad <emphasis>Hatter</emphasis>`
  are not the phrase. A tag must have well-formed attributes to count
  (`fb2_structure.markup_tags`): `a<b and c>d` and pandoc-escaped
  `\<Skill acquired: Spidergun\>` are text. XML entities (`&amp;`, `&#38;`) are not
  words (a term `amp` never matches inside `&amp;`), and a markdown
  reference definition needs a URL-like target: `[Level]: 5 Hatter` is text.
- Two words match when they share a key: casefolded form, NLTK Snowball
  stem (en, ru, de, fr, es, it, pt, nl, sv, da, nb, fi, ro, hu, ar) or the
  spaCy lemma of the chunk word. `spidergun` finds `spiderguns`,
  `паукопушка` finds `паукопушками`, `wolf` finds `wolves` (lemma).
- Terms in scripts without spaces between words (Chinese, Japanese, Thai,
  …) and Korean (particles glued to nouns: `철수는`) are matched as
  substrings.
- A term never matches inside an unrelated word (`Ann` ≠ `Annoying`).
- Stems and lemmas that are stop words are ignored, so a name ending in -s
  does not collapse onto a common word (`Ares` ≠ `are`, `Wells` ≠ `well`).
  Rare stem collisions remain possible (`universe`/`university`); they only
  add an extra glossary line to the prompt.

spaCy runs once on the chunk; its lemmas feed stage 1 (a single
`find_terms` pass over surface forms, stems and lemmas), and its word vectors
feed stage 2 for the terms still unmatched. With `NER=false`, or if the spaCy
model cannot be loaded, only the spaCy-free search runs (surface forms +
stems).

Stop words used when building a dictionary come from `lexicon.get_stop_words()`:
NLTK list (≈30 languages) ∪ spaCy list (every spaCy language, incl. ja, ko,
pl, uk, hr, lt, mk) for the source language, plus fiction-specific extras for
English. They are casefolded, so look words up with `lexicon.is_stop_word()`
(German `daß` → `dass`).

## 🏗 Building a Dictionary

`VocabularyManager.build_dictionary()` builds every dictionary — a translation
run of any format and `--build-dict`; `--build-series-dict` uses
`ner.create_series_vocab()`. Both:

- extract named entities with NER (frequent ordinary words only with
  `DICT_FREQUENT_WORDS=true` / `--frequent-words`);
- translate the terms with the **proofread** LLM;
- write the `.dic` atomically once every chunk is translated, so a failed or
  interrupted build leaves no half-written dictionary for the next run.

The book's own languages are used (the Calibre pipeline passes the languages
of `run_pipeline()`; default `SOURCE_LANG`/`TARGET_LANG`/`COUNTRY`).
`--build-dict` runs NER even with `NER=false`. The series dictionary groups
entity forms by the lemmas of all their words and writes the form that is its
own lemma (else the most frequent one) with its original capitalization:
`John Smith`, `Иван` — not `john`.

## 🧠 Cosine Similarity Matching (stage 2)

Terms not found in stage 1 are compared by word vectors.

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

- **2026-10-02:** Multi-word terms take priority (`lexicon.resolve_terms`, `term_rank`); substitution into the source rewritten (`term_substitution.py`); Korean particles stripped from entities; `[cjk]` extra
- **2026-10-01:** One matcher for all formats (Calibre pipeline now uses `VocabularyManager`); lexical stage matches inflected forms and CJK without regex; stop words for the source language instead of English only
- **2026-03-29:** Added CPU fallback mode (`find_matching_words_with_cosine_similarity_cpu()`)
- **2026-03-29:** Automatic GPU/CPU detection in `get_vocab_for_chunk()`
- **Previous:** Initial NER implementation with GPU support


## Substitution before the first stage

`src/term_substitution.py` (`replace_vocab_in_text`) replaces the terms of
the chunk in the source text before Stage 1, so the model cannot skip them.
It follows the matching rules above: the same priority, the same notion of
markup (tags, link targets, URLs and attribute blocks are never touched, no
term across them); occurrences never overlap. Words may be separated by any
whitespace, apostrophes may be typographic, CJK terms need no word
boundaries; a Latin term inside CJK text (`ABC社の製品`, also full-width
`ＡＢＣ`) is a word of its own. A lowercase term matches in any case (the target takes over the
capital), a term with capitals matches as written or in ALL CAPS (`Will` is
not replaced in "will"). In the classic pipeline (`style='xml'`) the chunk is
serialized FB2: terms are looked up and targets inserted XML-escaped
(`AT&amp;T`, `Б&amp;К`). Inflected forms (`Hatters`) are not substituted —
the model gets them through the glossary lines of the prompt. Stages 2–4
see the original.

## CJK sources

- **Models** (`SOURCE_LANG` picks them, `NERMODEL` overrides): `ko_core_news_lg`,
  `ja_core_news_lg`, `zh_core_web_lg`. Japanese and Chinese need their
  tokenizers (`pip install -e ".[cjk]"`: sudachipy, sudachidict-core,
  spacy-pkuseg); Korean uses spaCy's own tokenizer. Checked with all three
  models: lexical match, lemmas, cosine stage, entity extraction and
  substitution.
- **Stop words:** NLTK (Chinese) ∪ spaCy lists of the language, so Chinese
  has ~1800 entries, Japanese ~160, Korean ~65, Thai 7. Terms in unspaced
  scripts are matched as substrings and are not filtered by stop words
  (the dictionary is what the user reviewed); stop words only filter NER
  output and candidates.
- **Korean particles:** the Korean model tags `철수는` as `ncn+jxt` with the
  lemma `철수+는`. `ner.entity_text` cuts the trailing particle (tag `j*`)
  of the entity's last word, so the `.dic` gets `철수`, `서울`, `영희` and
  not one inflected form. The lemmatizer stays enabled for Korean only.
  A short name still matches inside a longer one (`철수` in `김철수`): that
  is the price of substring matching for glued particles.
- **Priority** works the same: `魔王城` beats `魔王` where they overlap, and a
  line break inside a term is not skipped (`魔王⏎城` is not `魔王城`).
- **Known limits:** NER quality depends on the model (`韩梅梅` may come out as
  `韩梅`); `ner.known_words` filters coined one-word terms by word vectors,
  so a word the model knows (`거미총` in ko) is treated as an ordinary word.
