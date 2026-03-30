# Sunny Narrator v1.9

Dual-LLM translation system with 5-stage quality control.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Edit .env with your API keys and model settings

# Run translation
python app.py
```

## 📋 Configuration

### .env File

```bash
# Primary LLM (Translation)
MODEL_TRANSLATE=google/gemma-2-27b-it
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
S_PROMT_TRANSLATE=true          # ⚠️ true для Gemma 2/3!
TEMP_TRANSLATE=0.01             # Base temperature (fallback)

# Secondary LLM (Proofreading)
MODEL_PROOFREAD=Mistral
API_BASE_PROOFREAD=http://localhost:11434/v1
API_KEY_PROOFREAD=your-key
S_PROMT_PROOFREAD=false         # false для Mistral/Llama
TEMP_PROOFREAD=0.7              # Base temperature (fallback)

# Stage-Specific Temperatures (NEW!)
TEMP_INITIAL=0.01               # Stage 1: Primary LLM - Translation
TEMP_REFLECTION=0.4             # Stage 2: Secondary LLM - Analysis
TEMP_IMPROVE=0.4                # Stage 3: Secondary LLM - Editing
TEMP_FINAL_EDIT=0.15            # Stage 4: Secondary LLM - Proofreading
TEMP_SYNOPSIS=0.15              # Stage 5: Secondary LLM - Summary

# Languages
SOURCE_LANG=english
TARGET_LANG=russian
COUNTRY=Россия

# Processing
MAX_LEN_CHUNK=8192
LENGTH_CHECK_THRESHOLD=20       # Rechunk if length differs by >20%
FAST_TRANS=false                # Fast translation mode (skip quality stages)
DEBUG=off
```

## ⚡ FAST_TRANS Mode

### When to use `FAST_TRANS=true`:

| Use Case | Recommended | Reason |
|----------|-------------|--------|
| **Draft translation** | ✅ **YES** | Fast, good enough for review |
| **Technical docs** | ✅ **YES** | Less style-sensitive |
| **Final publication** | ❌ No | Use full 5-stage pipeline |
| **Literary translation** | ❌ No | Quality stages important |

### What it does:

**FAST_TRANS=false** (Standard, 5 stages):
```
Stage 1: INITIAL (Primary LLM)       → Translation
Stage 2: REFLECTION (Secondary LLM)  → Quality review
Stage 3: IMPROVE (Secondary LLM)     → Apply suggestions
Stage 4: FINAL_EDIT (Secondary LLM)  → Proofreading
Stage 5: SYNOPSIS (Secondary LLM)    → Summary
```

**FAST_TRANS=true** (Fast, 2 stages):
```
Stage 1: INITIAL (Primary LLM)       → Translation
Stage 5: SYNOPSIS (Secondary LLM)    → Summary
(Stages 2-4 skipped)
```

### Performance comparison:

| Mode | Stages | LLM Calls | Speed | Quality |
|------|--------|-----------|-------|---------|
| **Standard** | 5 | 5 (1 Primary + 4 Secondary) | 1.0x | High |
| **FAST_TRANS** | 2 | 2 (1 Primary + 1 Secondary) | ~2.5x faster | Medium |

### Configuration:

```bash
# Fast mode - Primary LLM only, no iterative improvement
FAST_TRANS=true

# Standard mode - Full 5-stage pipeline
FAST_TRANS=false
```

### Use cases:

**FAST_TRANS=true:**
- Quick drafts for review
- Internal documentation
- Technical manuals
- Content where speed > style

**FAST_TRANS=false:**
- Literary translation
- Published books
- Style-sensitive content
- Final versions

## 🔧 sys_not_promt Mode

### When to use `S_PROMT_TRANSLATE=true` or `S_PROMT_PROOFREAD=true`:

| Model Family | Set to `true`? | Reason |
|--------------|----------------|--------|
| **Gemma 2** (google/gemma-2-9b-it, google/gemma-2-27b-it) | ✅ **YES** | Doesn't support system role |
| **Gemma 3** (google/gemma-3-12b-it) | ✅ **YES** | Doesn't support system role |
| **Mistral** (Mistral-7B, Mistral-Large) | ❌ No | Supports system role |
| **Llama 3.2/3.3** | ❌ No | Supports system role |
| **Hunyuan** | ❌ No | Supports system role |
| **Qwen** | ❌ No | Supports system role |

### What it does:

- **false** (default): Sends system and user prompts as separate messages
  ```json
  [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
  ```

- **true**: Merges system prompt into user prompt
  ```json
  [{"role": "user", "content": "system_prompt\n\nuser_prompt"}]
  ```

## 🔧 JSON Mode Control

### When to use `DISABLE_JSON_MODE_TRANSLATE` and `DISABLE_JSON_MODE_PROOFREAD`:

| Model Family | Set to `false`? | Reason |
|--------------|-----------------|--------|
| **Gemma 2/3** | ❌ No (keep `true`) | Struggles with JSON mode, use plain text |
| **Mistral** | ❌ No (keep `true`) | May return empty responses in JSON mode |
| **Llama 3.x** | ❌ No (keep `true`) | Local versions often fail JSON mode |
| **Hunyuan** | ✅ **YES** | Supports JSON mode correctly |
| **Qwen** | ✅ **YES** | Supports JSON mode correctly |
| **OpenAI/GPT** | ✅ **YES** | Supports JSON mode correctly |

### What it does:

- **true** (default): Disables `response_format={"type": "json_object"}` — LLM returns plain text
- **false**: Enables JSON mode — LLM must return valid JSON

### Configuration:

```bash
# Default: JSON mode disabled (safer for local LLMs)
DISABLE_JSON_MODE_TRANSLATE=true
DISABLE_JSON_MODE_PROOFREAD=true

# For API models that support JSON mode:
DISABLE_JSON_MODE_TRANSLATE=false
DISABLE_JSON_MODE_PROOFREAD=false
```

### Empty Response Handling

When JSON mode is disabled or LLM returns empty response:
- **Automatic retry**: Up to 2 retries with ERROR logging
- **Debug output**: Original content logged when `remove_tags()` results in empty text
- **Error format**: `ERROR - Ответ 0 [stage/role]: X chars → 0 chars after remove_tags`

| Model Family | Set to `true`? | Reason |
|--------------|----------------|--------|
| **Gemma 2** (google/gemma-2-9b-it, google/gemma-2-27b-it) | ✅ **YES** | Doesn't support system role |
| **Gemma 3** (google/gemma-3-12b-it) | ✅ **YES** | Doesn't support system role |
| **Mistral** (Mistral-7B, Mistral-Large) | ❌ No | Supports system role |
| **Llama 3.2/3.3** | ❌ No | Supports system role |
| **Hunyuan** | ❌ No | Supports system role |
| **Qwen** | ❌ No | Supports system role |

### What it does:

- **false** (default): Sends system and user prompts as separate messages
  ```json
  [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
  ```

- **true**: Merges system prompt into user prompt
  ```json
  [{"role": "user", "content": "system_prompt\n\nuser_prompt"}]
  ```

## 📊 Translation Workflow (5 Stages)

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: INITIAL (Primary LLM)                              │
│ - Translate with vocabulary and context                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: REFLECTION (Secondary LLM)                         │
│ - Quality review with country/language awareness            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: IMPROVE (Secondary LLM)                            │
│ - Apply reflection suggestions                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: FINAL_EDIT (Secondary LLM) 🆕                       │
│ - Compare with original, restore XML tags                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: SYNOPSIS (Primary LLM) ← from FINAL translation    │
│ - Create summary for next chunk context                     │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
sunny-narrator/
├── app.py                      # Main controller
├── src/
│   ├── utils.py                # Translation pipeline (5 stages)
│   ├── prompts.json            # All prompts (Primary/Secondary LLM)
│   ├── config.py               # Configuration + sys_not_promt flags
│   ├── fb2_handler.py          # FB2 file operations
│   ├── epub_handler.py         # EPUB parsing
│   ├── txt_handler.py          # TXT parsing
│   ├── xml_utils.py            # Common XML utilities
│   ├── xmlcheck.py             # XML validation
│   ├── vocabulary_manager.py   # Terminology dictionaries
│   ├── character_registry.py   # Character tracking
│   ├── synopsis_manager.py     # Synopsis generation
│   ├── ner.py                  # spaCy NER
│   └── epub_writer.py          # EPUB creation
├── docs/
│   └── PROMPTS_GUIDE.md        # Detailed prompts documentation
└── .env                        # Configuration (gitignored)
```

## 🎯 Prompts

All prompts are in `src/prompts.json`:

### Primary LLM Prompts
- `initial_translation` — Translation with context
- `synopsis` — Summary generation

### Secondary LLM Prompts
- `reflection` — Quality review
- `improve` — Apply suggestions
- `editor` — Final proofreading (Stage 5)

### Utilities
- `vocabulary` — Term translation
- `metadata_translation` — Book metadata
- `image_generation` — Cover generation

See [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) for details.

## 📎 Vocabulary Management

Sunny Narrator uses a dictionary file (`*.dic`) to ensure terminology consistency.

### Dictionary Format (JSON)

```json
# Vocabulary for MyBook
[
  {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she", "notes": "Main character"},
  {"source": "Wonderland", "target": "Страна Чудес", "category": "LOC", "gender": "", "notes": ""}
]
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `source` | ✅ | Term in source language |
| `target` | ✅ | Translation |
| `category` | ⚪ | `PERSON`, `LOC`, `ORG`, `TERM` |
| `gender` | ⚪ | `he`, `she`, `it`, `they` |
| `notes` | ⚪ | Comments |

### Workflow

1. **Automatic creation:** NER extracts terms on first run
2. **Manual editing:** Edit `.dic` file before translation
3. **Validation:** `python -c "from src.vocabulary_manager import validate_dictionary; print(validate_dictionary('books/mybook.dic'))"`

**See also:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 🧪 Testing

```python
from src.utils import translate_chunk

result, synopsis = translate_chunk(
    source_lang='english',
    target_lang='russian',
    source_text='<p>Hello World</p>',
    outline_text='',
    vocab_dict={},
    country='Россия',
    style='xml',
    fast_mode=False
)

print(f"Translation: {result}")
print(f"Synopsis: {synopsis}")
```

## 📝 Versions

- **v1.9** — 5-stage pipeline, stage-specific temperatures, profanity preservation
- **v1.8** — Rechunking with length validation
- **v1.7** — NER with CPU fallback
- **v1.0** — Initial release

## 📝 Changelog

### 2026-03-29 (v1.9)
- ✅ 5-stage translation pipeline (INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → SYNOPSIS)
- ✅ Stage-specific temperatures (TEMP_INITIAL, TEMP_REFLECTION, etc.)
- ✅ sys_not_promt mode for Gemma 2/3
- ✅ Dictionary format with commas (source = target, category, gender, notes)
- ✅ NER with CPU fallback (avoid NVRTC errors)
- ✅ Rechunking with length validation
- ✅ FAST_TRANS mode (skip stages 2-4 for speed)
- ✅ Profanity preservation in prompts
- ✅ remove_tags() strips <vocabulary>, <synopsis> sections
- ✅ Comprehensive documentation (8 guide files)

### Previous (v1.0)
- Dual-LLM pipeline implementation
- Hunyuan-specific prompt support
- Country/language awareness in prompts

## 📄 License

Open Source
