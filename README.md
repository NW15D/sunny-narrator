# Sunny Narrator

**Version:** 1.15  
Book translation program for FB2/EPUB formats. You can use just only Qwen3.5-35B-A3B for both endpoints.
Dual-LLM translation system with 5-stage quality control.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Edit .env with your API keys

# Run translation (JSON mode recommended)
python app.py
```

**Full documentation:** [docs/](docs/)

---

## 📋 Configuration

### Basic .env

```bash
# API Settings
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it
JSON_MODE=true    # 🚀 Recommended: structured JSON for all stages

API_KEY_PROOFREAD=your-key
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Mistral

# Languages
SOURCE_LANG=english
TARGET_LANG=russian

# Processing
FAST_TRANS=false    # Fast mode (skip quality stages)
DEBUG=off
```

**All options:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS Mode

**Use `FAST_TRANS=true` for:**
- ✅ Draft translation
- ✅ Technical docs
- ❌ NOT for final publication or literary translation

**Speed:** ~2.5x faster (2 stages instead of 5)

**Details:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 Vocabulary

Dictionary file (`*.dic`) ensures terminology consistency:

```dic
# Format: source = target, category, gender, notes
Alice = Алиса, PERSON, she, Main character
```

**Format guide:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 📖 Glossary-Driven Translation (Series of Books)

Create a unified dictionary for a series of books to ensure consistent terminology across all volumes.

### Build Series Dictionary

```bash
# Basic usage
python app.py --build-series-dict books/ --series-dict-output series.dic

# With custom thresholds
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --min-count-word 5
```

**Parameters:**
- `--build-series-dict` — Path to folder containing FB2/EPUB/TXT books
- `--series-dict-output` — Output dictionary file (default: `series.dic`)
- `--min-count-ner` — Minimum occurrences for NER entities (default: 5)
- `--min-count-word` — Minimum occurrences for common words (default: 10)

**Workflow:**
1. Find all book files in folder
2. Extract text from each book
3. Run NER to find named entities (PERSON, ORG, LOC, GPE)
4. Aggregate counts across all books
5. Filter by threshold criteria
6. Translate terms via LLM
7. Save unified `.dic` file

**Output:** JSON-format dictionary with `book_origin` field showing which book each term came from.

---

## 💾 Resume after Crash

Automatic progress saving after each chunk:

```bash
# Interrupted at 50%
python app.py  # Ctrl+C

# Resume automatically
python app.py  # ✓ Resuming from chunk 51/100
```

**Details:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**CPU-only (default):**
```bash
docker-compose up -d
```

**GPU (NVIDIA):**
```bash
docker-compose -f docker-compose.gpu.yml up -d
```

**Guide:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)

---

## 📚 Documentation

| Topic | File |
|-------|------|
| **Installation** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Configuration** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **FAST_TRANS Mode** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Translation Stages** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Temperature Strategy** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Rechunking** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Dictionary Format** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Resume after Crash** | [docs/RESUME.md](docs/RESUME.md) |
| **Docker (CPU/GPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **JSON Mode Analysis** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) — JSON mode implementation details, input/output formats
| **NER CPU Fallback** | [docs/NER_CPU_FALLBACK_ANALYSIS.md](docs/NER_CPU_FALLBACK_ANALYSIS.md) |
| **Prompts Guide** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 Versions

- **v1.11** — Checkpoint/resume, empty response fallback, CPU Docker
- **v1.10** — remove_tags simplification, token stats fix
- **v1.9** — 5-stage pipeline, stage-specific temperatures
- **v1.0** — Initial release

---

[Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md)
