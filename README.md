# Sunny Narrator

**Early-stage AI translator for long texts** (FB2, EPUB, TXT)

![sh.png](sh.png)

**Quick start:** For fastest free translation, use [Hunyuan (Tencent)](https://huggingface.co/tencent/HY-MT1.5-7B-GGUF) or [TranslateGemma (Google)](https://huggingface.co/google) — 5-12GB VRAM required.

---

## Features

- Vocabulary translation
- Proofreading
- Synopsis for consistent translation
- Regional nuances
- Humor and obscene content preservation
- Length and error checking with auto-fix
- Concurrent translation and proofreading via 2 API/LLM
- Cover book with image generation
- Metadata translation for FB2 and EPUB
- Docker support

---

## Requirements

1. **Hardware:** CUDA-enabled GPU with NVIDIA driver (2GB+ VRAM), or Docker
2. **API:** OpenAI-compatible API (llama.cpp, OpenAI, Claude, etc.)
3. **Input:** FB2 or TXT file (EPUB converts to FB2)
4. **Runtime:** Docker or Python 3.10+

---

## Configuration

Create `.env` file:

### General Settings

| Variable | Description | Default |
| :--- | :--- | :--- |
| `FILE` | Input file path | `books/Cargo.fb2` |
| `SOURCE_LANG` | Source language | `english` |
| `TARGET_LANG` | Target language | `russian` |
| `COUNTRY` | Target country for context | `Россия` |
| `MAX_LEN_CHUNK` | Max chunk size (tokens) | `8192` |
| `FAST_TRANS` | Fast mode (skip reflection) | `on` |
| `DEBUG` | Verbose logging | `off` |

### Translation API (Primary)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_TRANSLATE` | API key | `your-key` |
| `API_BASE_TRANSLATE` | API URL | `http://localhost:6155/v1` |
| `MODEL_TRANSLATE` | Model name | `Hunyuan` |
| `TEMP_TRANSLATE` | Temperature | `0.01` |
| `TIMEOUT_TRANSLATE` | Timeout (seconds) | `6000` |

### Proofreading API (Secondary)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_PROOFREAD` | API key | `your-key` |
| `API_BASE_PROOFREAD` | API URL | `http://localhost:6150/v1` |
| `MODEL_PROOFREAD` | Model name | `Ministral8b` |
| `TEMP_PROOFREAD` | Temperature | `0.01` |

### Images API (Cover)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_IMAGES` | API key | `''` |
| `MODEL_IMAGES` | Model name | `gpt-image-1.5` |

### Advanced

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NER` | Auto-vocabulary (NER) | `True` |
| `NERMODEL` | spaCy model | `en_core_web_lg` |

---

## Source Languages

Supported by spaCy: `en`, `ru`, `zh`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `cs`, `pl`, `uk`, `tr`, `nl`

Target languages: Any 2-letter code (LLM-dependent)

---

## Launch

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```

**First run:** Test on a file with ≤100 words.

---

## XML Tag Preservation Fix (2026-03-27)

**Problem:** Previous implementation used XML tag masking with markers `@@@TAG_n@@@`, causing 100% marker loss during translation.

**Solution:** Direct translation with XML tags + post-processing validation.

### Changes

| Component | Before | After |
|-----------|--------|-------|
| **Approach** | Tag masking with markers | Direct XML translation |
| **Tag loss** | 100% chunks | < 5% (expected) |
| **Code** | +651 lines | -600 lines |
| **Prompts** | 25+ instruction lines | 5 lines |
| **Tokens** | +20% overhead | 0% overhead |

### Architecture

**Before:**
```
chunk → mask_xml() → translate() → editor() → unmask_xml() → validate()
```

**After:**
```
chunk → translate() → editor() → post_process_xml() → validate_xml()
```

### post_process_xml()

New function for XML validation and repair:

1. **XML validation** via `xc.rem_tags()` — artifact cleanup
2. **Tag counting** — compare original vs translated
3. **LLM repair** — if difference > 10%, restore via LLM

```python
def post_process_xml(source_text, translated_text):
    cleaned = xc.rem_tags(translated_text)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        cleaned = llm_repair_xml(source_text, cleaned)
    return cleaned
```

### Documentation

- **Spec:** `docs/specs/2026-03-27-xml-tag-preservation-design.md`
- **Plan:** `docs/plans/2026-03-27-xml-tag-preservation.md`
- **Changelog:** `docs/CHANGELOG_XML_FIX.md`

### Testing

```bash
# Quick test
python3 app.py 2>&1 | tee test_example.log

# Check tag loss
python3 -c "
import re
with open('books/ExampleBook.fb2', 'r') as f:
    orig = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
with open('books/ExampleBook_translated.fb2', 'r') as f:
    trans = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
print(f'Tag loss: {(orig-trans)/orig*100:.2f}% (target: < 5%)')
"
```

**Expected result:** Tag loss < 5%

---

## Thanks

- [POC](https://github.com/andrewyng/translation-agent) — automated FB2 translation via LLM agents
- Qwen_Coder32B — wonderful model
- Antigravity — awesome

---

## For Your Information

Made for fun and home use. This project could become a real product with dozens of ideas for quality improvement. Commercial services exist (e.g., www.inotherword.ai), but building a robust commercial app requires Java, Kafka/RabbitMQ, Postgres, Minio, specialized LLMs — 3-6 months and significant investment.

---

## Other Languages

- [🇷🇺 Russian](README_RU.md)
- [🇨🇳 Chinese](README_CN.md)
- [🇧🇷 Portuguese](README_PT.md)
