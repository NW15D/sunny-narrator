# Configuration Guide — Complete Parameter Reference

**Version:** 1.11  
**Date:** 2026-03-30

---

## 📋 Overview

The `.env` file contains all configuration parameters for Sunny Narrator.

**Minimal configuration:**
```bash
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it

SOURCE_LANG=english
TARGET_LANG=russian
```

---

## 🔧 API Settings

### Primary LLM (Translation)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_TRANSLATE` | — | API key for Primary LLM |
| `API_BASE_TRANSLATE` | `http://localhost:11434/v1` | Base URL for API |
| `MODEL_TRANSLATE` | `Mistral` | Model for translation |
| `S_PROMT_TRANSLATE` | `false` | `true` for Gemma 2/3 (do not support system prompts) |
| `TEMP_TRANSLATE` | `0.01` | Base temperature (fallback) |
| `TIMEOUT_TRANSLATE` | `6000` | Request timeout (seconds) |
| `DISABLE_JSON_MODE_TRANSLATE` | `true` | ~~Disable JSON mode~~ **DEPRECATED** — use `JSON_MODE` |
| `JSON_MODE` | `false` | Enable structured JSON for all stages (**recommended**) |

### Secondary LLM (Proofreading)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_PROOFREAD` | — | API key for Secondary LLM |
| `API_BASE_PROOFREAD` | `https://api.openai.com/v1` | Base URL for API |
| `MODEL_PROOFREAD` | `tencent/Hunyuan-MT-7B` | Model for proofreading |
| `S_PROMT_PROOFREAD` | `false` | `true` for Gemma 2/3 |
| `TEMP_PROOFREAD` | `0.7` | Base temperature (fallback) |
| `TIMEOUT_PROOFREAD` | `6000` | Request timeout (seconds) |
| `DISABLE_JSON_MODE_PROOFREAD` | `true` | ~~Disable JSON mode~~ **DEPRECATED** — use `JSON_MODE` |

> ⚠️ **Legacy flags:** `DISABLE_JSON_MODE_TRANSLATE` and `DISABLE_JSON_MODE_PROOFREAD` are deprecated.
> When `JSON_MODE=true`, JSON is enabled for all stages automatically.
> Legacy flags maintain backward compatibility but may be removed in future versions.

### Stage-Specific Temperatures

| Parameter | Default | Stage | Description |
|-----------|---------|-------|-------------|
| `TEMP_INITIAL` | `TEMP_TRANSLATE` | 1 | Initial translation (consistency) |
| `TEMP_REFLECTION` | `0.4` | 2 | Quality review (creative analysis) |
| `TEMP_IMPROVE` | `0.4` | 3 | Apply suggestions (flexible editing) |
| `TEMP_FINAL_EDIT` | `0.15` | 4 | Final proofreading (precision) |
| `TEMP_SYNOPSIS` | `0.15` | 5 | Synopsis generation (accuracy) |

**More details:** [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md)

---

## 🌍 Languages

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SOURCE_LANG` | `english` | Source language |
| `TARGET_LANG` | `russian` | Target language |
| `COUNTRY` | `Russia` | Country for localization |

---

## ⚡ Processing

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_LEN_CHUNK` | `8192` | Maximum chunk size (characters) |
| `LENGTH_CHECK_THRESHOLD` | `20` | Rechunking threshold (%) |
| `FAST_TRANS` | `false` | Fast mode (skip stages 2-4) |
| `DEBUG` | `off` | Debug mode |

**More details:** [FAST_TRANS.md](FAST_TRANS.md), [RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md)

---

## 📎 NER (Named Entity Recognition)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NER` | `true` | Enable NER processing |
| `NERMODEL` | `en_core_web_lg` | spaCy model for NER |

**More details:** [NER_GUIDE.md](NER_GUIDE.md), [NER_CPU_FALLBACK_ANALYSIS.md](NER_CPU_FALLBACK_ANALYSIS.md)

---

## 🐳 GPU/CPU

| Parameter | Default | Description |
|-----------|---------|-------------|
| `GPU` | `true` | Use GPU if available |
| `SPACY_USE_GPU` | `false` | Force CPU for spaCy |

**More details:** [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md)

---

## 🖼️ Images (Cover)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_IMAGES` | — | API key for image generation |
| `API_BASE_IMAGES` | — | Base URL for images |
| `MODEL_IMAGES` | `gpt-image-1.5` | Model for generation |

---

## 📝 Configuration Examples

### Local LLM (Ollama)

```bash
API_KEY_TRANSLATE=ollama
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=gemma2:27b
S_PROMT_TRANSLATE=true
JSON_MODE=true

API_KEY_PROOFREAD=ollama
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=mistral:7b
S_PROMT_PROOFREAD=false

GPU=false
NER=true
```

### API (OpenAI/Hunyuan)

```bash
API_KEY_TRANSLATE=sk-xxx
API_BASE_TRANSLATE=https://api.openai.com/v1
MODEL_TRANSLATE=gpt-4
JSON_MODE=true

API_KEY_PROOFREAD=sk-xxx
API_BASE_PROOFREAD=https://api.openai.com/v1
MODEL_PROOFREAD=gpt-4

GPU=true
NER=true
```

### CPU-only (no GPU)

```bash
GPU=false
SPACY_USE_GPU=false
NER=true

# Other parameters use defaults
```

---

## 🧩 JSON Mode

**JSON mode** enables structured input/output format for all 4 translation stages (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT).

### Enabling
```bash
JSON_MODE=true
```

### Advantages
- More reliable parsing (no XML tag conflicts)
- Structured input: vocabulary, synopsis, context in JSON
- Consistent output format across all stages

### Behavior
When `JSON_MODE=true`:
- All stages use JSON prompts from `prompts.json` (categories with `_json` suffix)
- LLM output is parsed as JSON
- On parsing error — automatic fallback to XML mode

### Details
- [JSON Mode Analysis](JSON_MODE_ANALYSIS.md) — full documentation on input/output formats
- Prompt categories: `initial_translation_json`, `reflection_json`, `improve_json`, `editor_json`
- In JSON prompts, curly braces are escaped: `{{ "translation": "..." }}`

---

## 🔍 Debugging

### Enable DEBUG mode

```bash
DEBUG=on
```

**What is logged:**
- LLM requests/responses
- Chunk processing time
- Token statistics
- NER extraction
- Vocabulary matching

### Verify configuration

```bash
python3 -c "from src.config import Config; c = Config(); print(f'NER: {c.ner_opt}, GPU: {c.gpu_enabled}')"
```

---

## 📚 Related documentation

- [INSTALLATION.md](INSTALLATION.md) — Installation
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-stage pipeline
- [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md) — Temperatures
- [NER_GUIDE.md](NER_GUIDE.md) — NER processing
- [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md) — Docker configuration

---

**Version:** 1.11  
**Updated:** 2026-03-30
