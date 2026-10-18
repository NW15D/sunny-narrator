# Sunny Narrator

**English** | [Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — translate EPUB, PDF, TXT, FB2 and DOCX books into many languages" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Version:** 2.9.4  
**Glossary-Driven AI Book Translator** for FB2/TXT/EPUB/DOCX/PDF — an LLM-powered fiction book translator with dual-LLM translation and 5-stage quality control.

🖥️ **Console app (CLI)** — no graphical interface; basic command-line experience is recommended.

**Why it is worth a try:**
- 📚 **Glossary-driven** — a `.dic` dictionary keeps terminology consistent across a whole book and a whole series
- 🔨 **Extended dictionary work** — the dictionary can be verified against the book (`dict review`, `dict clean`), it is validated before every run, and it **automatically tries to fix the category and the gender** of every entry from the book itself (`DICT_AUTOFIX`)
- 🔁 **Dual-LLM, 5 stages** — one LLM translates, a second one reviews and polishes; every chunk passes INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- 💻 **Local GPUs (16-24GB VRAM)** via llama.cpp, Ollama, LM Studio etc. and any OpenAI-compatible API (3-4M tokens per book), or ☁️ any hosted API
- 💾 **Crash-proof** — progress checkpoints after every chunk, a resumed run continues where it stopped
- 🎓 For professional and non-professional translators alike — drafts and dictionaries included

## 🚀 Quick Start — first translation in 5 steps

1. **Clone and install**
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   pip install -e .
   # DOCX/EPUB/PDF input also needs: sudo apt install pandoc calibre
   ```
2. **Configure** — `cp env.sample .env`, fill in `API_KEY_*`, `API_BASE_*`, `MODEL_*`, `SOURCE_LANG`, `TARGET_LANG`, `FILE=books/mybook.fb2`. Formats are auto-detected by extension (FB2/TXT → classic pipeline, DOCX/EPUB/PDF → Calibre pipeline).
3. **Build the dictionary** — `python app.py` creates `books/mybook.dic` and stops for review.
4. **Edit the dictionary** — remove errors, fix translations and genders (the run tells you what is unsure).
5. **Translate** — run `python app.py` again; the result appears next to the source file with a language marker. Then proofread the book.

**CPU-only or GPU without conda?** Use Docker (next section). **Draft without review stages?** `FAST_TRANS=true` (~2.5x faster).

## 🐳 Docker

Pre-built images (both include Calibre and pandoc; built from `Dockerfile` / `Dockerfile.cpu`, tested on every push to `main`):

```bash
# 1. Pull the image (GPU or CPU-only)
docker pull ghcr.io/nw15d/sunny-narrator:main        # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu    # CPU

# 2. Prepare the folders and the config (run these on the host)
mkdir -p books output logs
cp env.sample .env
# edit .env: API keys, MODEL_*, SOURCE_LANG/TARGET_LANG, FILE=books/mybook.fb2
cp mybook.fb2 books/

# 3. Run — first pass builds books/mybook.dic, review it, run again to translate
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# CPU image: drop --gpus all and use ...sunny-narrator:main-cpu
```

Alternative with compose (config `.env` is read automatically): `docker-compose up -d` (GPU) or `docker-compose -f docker-compose.cpu.yml up -d`.

**Guides:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md), [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

## 📋 Configuration

`env.sample` is a complete, documented reference: every parameter of the system is listed there with its description and default, and the end of the file has ready-made variants (two llama.cpp servers, one Ollama, English source, FB2 → EPUB, fast draft). Key options:

```bash
API_KEY_TRANSLATE=your-api-key-here     # any non-empty string for a local server
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # translate LLM (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # proofread LLM (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru
OUTPUT_FORMAT=fb2                       # fb2|epub for FB2/TXT; epub|docx|pdf for EPUB/DOCX/PDF
```

**All options:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Dictionary (the heart of the quality)

- The first run builds `book.dic` automatically: the spaCy model of the source language finds names; categories and genders are decided by the book itself, the LLM only translates.
- Before every translation the dictionary is **checked against the book** (no LLM): sure findings fix the category/gender for that run; the `.dic` itself is never silently changed — `<dic>.reviewed.dic` gets them.
- `PERSON` entries carry a gender into every stage prompt and are enforced by the GENDER stage; put races/species/coined words as `TERM`.
- Series-wide dictionary: `--build-series-dict`, then one `series.dic` for all volumes (`DICTIONARY=series.dic`).
- Standalone tools: `dict clean`, `dict review`, `dict convert`, `audit`.

**Commands, rules, series workflow, spaCy/CUDA/CJK nuances:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

## ✏️ Prompts

All stage prompts live in **`src/prompts.json`** — edit them to change translation style, tone and terminology behaviour: edits affect the quality of the whole pipeline (A/B them with `python app.py eval`). In Docker the file is mounted from the repo, so host-side edits take effect on the next run.

**Guide to every prompt:** [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md)

## ⚡ FAST_TRANS

`FAST_TRANS=true` (or `--fast-mode`) runs INITIAL + GENDER + SYNOPSIS only — ~2.5x faster, for drafts and technical docs, **not** for final publication. Tip: combine with `DICT_AUTO_SAVE=true`, review the dictionary, then re-translate with `--fresh` for quality. [Details](docs/FAST_TRANS.md)

## 💾 Resume, chunking and logging

- Crash or Ctrl+C: a plain `python app.py` resumes from the last checkpoint (`--fresh` restarts). [Details](docs/RESUME.md)
- Chunk length is auto-calibrated per book (median ratio of accepted chunks; first 3 chunks checked only for gross failures). [Details](docs/RECHUNKING_GUIDE.md)
- Console shows every step; `DEBUG=on`, `LLM_LOGGING=true` for full traces. [Details](docs/LOGGING.md)

## 📖 Glossary-driven series translation

```bash
python app.py --build-series-dict books/ --series-dict-output series.dic \
  # options: --min-count-ner 2  --frequent-words  --min-count-word 5
python app.py --dictionary series.dic   # per book; the run never changes series.dic
```

Step-by-step preparation of a series dictionary lives in [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#a-dictionary-shared-by-a-series).

## 📚 Documentation

| Topic | File |
|-------|------|
| **Installation** (incl. Calibre pipeline) | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Configuration** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Working with Dictionaries** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Translation Stages** (incl. GENDER) | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Prompts Guide** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |
| **FAST_TRANS Mode** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Temperature Strategy** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Rechunking** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Resume after Crash** | [docs/RESUME.md](docs/RESUME.md) |
| **Logging** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker (CPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker (GPU)** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **Tested Languages** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |

## 🈶 CJK sources (Korean, Japanese, Chinese)

Direct translation from CJK into any language is supported out of the box: `ja`/`zh` models need `pip install -e ".[cjk]"` (Korean needs nothing extra); terms match as substrings, Korean particles are cut when writing the dictionary, and the learned length ratio absorbs the 2-4x text growth. **Full nuances:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 Changelog

Release history: [CHANGELOG.md](CHANGELOG.md)
