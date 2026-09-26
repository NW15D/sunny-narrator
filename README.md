# Sunny Narrator

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Version:** 2.2  
**Glossary-Driven AI Book Translator** for FB2/TXT/EPUB/DOCX/PDF. Dual-LLM translation system with 5-stage quality control.

**Designed for:**
- 📚 Glossary-driven translation of book series (consistent terminology across volumes)
- 🔨 Dictionary creation for book and series translations
- 💻 Local GPUs (16-24GB VRAM) via llama.cpp, Ollama, LM Studio etc. — any OpenAI-compatible API (1-2M tokens per book)
- ☁️ Online translation services via API
- 👥 Character gender detection when the dictionary does not specify it (written back to the .dic and reused in later chunks)
- 📏 Automatic calibration of the post-translation chunk length check, based on the first 3 chunks
- 🈶 Adaptation for CJK languages (Korean, Japanese, Chinese)
- 🌐 Direct translation with dictionaries from CJK languages into any language

## 🔄 General Workflow

### Supported Formats

| Input Format | Pipeline |
|--------------|----------|
| **FB2, TXT** | Classic pipeline (direct XML — preserves poem/stanza/v structure) |
| **DOCX, EPUB, PDF** | Calibre pipeline (via HTMLZ intermediate) |

Pipeline selection is automatic based on file extension — no `--pipeline` flag needed.

```mermaid
flowchart LR
    A[1. Clone repo] --> B[2. Install dependencies]
    B --> C[3. Configure .env]
    C --> D[4. Point FILE to the book]
    D --> E[5. python app.py → book.dic]
    E --> F[6. Review/clean dictionary]
    F --> G[7. python app.py → translation]
    G --> H[8. Proofread the book]
```

**Step-by-step workflow:**
1. **Clone repository** — `git clone` the project
2. **Install dependencies** — `pip install -e .` (uses `pyproject.toml`); for DOCX/EPUB/PDF also install `pandoc` and `calibre`
3. **Configure** — create `.env` from `env.sample`, fill in API keys and `SOURCE_LANG`/`TARGET_LANG`
4. **Choose the book** — set `FILE=path/to/book.fb2` (or `.txt`, `.epub`, `.docx`, `.pdf`)
5. **Build the dictionary** — `python app.py` creates `book.dic` next to the book (the spaCy model for the source language is downloaded automatically). For FB2/TXT the run stops here for review; for DOCX/EPUB/PDF translation continues right away
6. **Edit dictionary** — review and clean up `book.dic` (remove errors, fix translations, set genders)
7. **Translate** — run `python app.py` again; the result is written next to the source file with a language marker in its name
8. **Read & proofread** — final review of the translated book

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install -e .

# Configure .env
cp env.sample .env
# Edit .env: API keys, SOURCE_LANG, TARGET_LANG

# FB2/TXT: the first run builds the dictionary, the second one translates
# DOCX/EPUB/PDF: dictionary and translation in one run
FILE=books/mybook.fb2 python app.py
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

# Book and languages
FILE=books/mybook.fb2
SOURCE_LANG=english
TARGET_LANG=russian

# Processing
FAST_TRANS=false    # Fast mode (skip quality stages)
DEBUG=off
```

**All options:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS Mode

**Use `FAST_TRANS=true` (or `--fast-mode`) for:**
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

- Created automatically on the first run via NER (named entities + frequent words), then translated by the LLM.
- **Character genders** (`he`, `she`, `it`, `they`): if the dictionary does not specify a gender, the synopsis stage determines it from the text and writes it into the `.dic`; characters missing from the dictionary are appended as `name = translation, PERSON, gender`. A gender already in the file is never overwritten, so manual edits always win.

**Format guide:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 🈶 CJK Languages (Korean, Japanese, Chinese)

Books can be translated directly from CJK languages into any language, with a dictionary:

- **NER:** `ko_core_news_lg` uses its own KLUE label scheme (`PS`/`LC`/`OG`) — it is recognized and normalized to `PERSON`/`LOC`/`ORG`.
- **Frequent words:** minimum word length is 2 characters instead of 5 (a CJK word is usually 1-3 characters).
- **Length check:** a CJK text grows 2-4x in characters when translated into alphabetic languages. The expected ratio is learned from the book itself — the median of accepted chunks; the first 3 chunks are only checked for gross failures (×0.25 … ×5).

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

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
- `--min-count-ner` — Minimum occurrences for NER entities (default: 2)
- `--min-count-word` — Minimum occurrences for common words (default: 5)

A dictionary for a single book can be built with `--build-dict path/to/book`.

**Workflow:**
1. Find all book files in folder
2. Extract text from each book
3. Run NER to find named entities (PERSON, ORG, LOC, GPE, EVENT, FAC, PRODUCT)
4. Aggregate counts across all books
5. Filter by threshold criteria
6. Translate terms via LLM
7. Save unified `.dic` file

**Output:** a regular `.dic` file (`source = target, category, gender, notes`).

---

## 💾 Resume after Crash

Automatic progress saving after each chunk:

```bash
# Interrupted at 50%
python app.py  # Ctrl+C

# Resume automatically
python app.py  # ✓ Resuming from chunk 51/100
```

For DOCX/EPUB/PDF, `--fresh` ignores the checkpoint and starts from scratch.

**Details:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**GPU (NVIDIA):**
```bash
docker-compose up -d
```

**CPU-only:**
```bash
docker-compose -f docker-compose.cpu.yml up -d
```

**Pre-built GPU image** ([GitHub Container Registry](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator), built from `Dockerfile` on every push to `main`):
```bash
docker pull ghcr.io/nw15d/sunny-narrator:main
```

**Guides:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md), [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

---

## 🔄 Calibre Pipeline (DOCX/EPUB/PDF)

Accepts **DOCX/EPUB/PDF** directly — no manual conversion needed.
The pipeline is auto-selected when you provide a file with `.docx`, `.epub`, or `.pdf` extension.

```bash
# Install system dependencies
sudo apt install pandoc calibre
pip install -e .

# Translate DOCX/EPUB/PDF (auto-detected by extension)
FILE=books/mybook.epub python app.py --output-format epub
```

**Pipeline:** DOCX/EPUB/PDF → Calibre → HTML → Markdown → Translate → HTML → Calibre → DOCX/EPUB/PDF

Calibre service markup (`calibre_link-*` anchors, `.calibre` classes) is removed automatically, and the table of contents is rebuilt from the translated headings.

> ⚠️ **FB2 is NOT supported by the Calibre pipeline.** FB2 has rich structure
> (poem/stanza/v) that Calibre's HTMLZ intermediate flattens into plain
> paragraphs — an irreversible quality loss. Use the **classic pipeline**
> (default for `.fb2` and `.txt` files) for FB2: it manipulates the XML directly
> and preserves all book structure.

**Full guide:** [docs/INSTALLATION.md](docs/INSTALLATION.md#-calibre-pipeline-auto-detected)

---

## 📜 Logging

The console log shows every step of the translation: length checks with the calibrated ratio, genders written to the dictionary, dictionary terms matched in the chunk, checkpoints.

![Console log of a Korean → Russian translation](logging.png)

- `DEBUG=on` — detailed log (length checks, dictionary matching, synopsis)
- `DEBUG_HTTP=on` — additionally, raw HTTP traces of the LLM clients
- `LLM_LOGGING=true` — every LLM call (prompts, response, tokens, timing) as JSON lines in `logs/llm_calls_YYYY-MM-DD.log` (directory: `LLM_LOGGING_DIR`)

**Details:** [docs/LOGGING.md](docs/LOGGING.md)

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
| **Logging** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker (CPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker (GPU)** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **Prompts Guide** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 Versions

- **v2.2** — Character gender detection written back to the dictionary; per-book calibration of the translation length check; CJK adaptation (Korean, Japanese, Chinese) with direct translation from CJK into any language
- **v2.1** — Auto-detect pipeline by file extension (.docx/.epub/.pdf → Calibre; .fb2/.txt → classic); removed `--pipeline` flag
- **v2.0** — Migrated from pip requirements.txt to pyproject.toml; PyTorch CUDA 12.1 + cuPy
- **v1.4** — Added general workflow diagram and step-by-step instructions to README
- **v1.3** — Initial English README
- **v1.11** — Checkpoint/resume, empty response fallback, CPU Docker
- **v1.10** — remove_tags simplification, token stats fix
- **v1.9** — 5-stage pipeline, stage-specific temperatures
- **v1.0** — Initial release

---

[Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md)
