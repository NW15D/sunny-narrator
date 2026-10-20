# Sunny Narrator

**English** | [Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — translate EPUB, PDF, TXT, FB2 and DOCX books into many languages" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Version:** 2.12.0  
**Glossary-Driven AI Book Translator** for FB2/TXT/EPUB/DOCX/PDF — an LLM-powered fiction book translator with dual-LLM translation and 5-stage quality control.

🖥️ **Console app (CLI)** — no graphical interface; basic command-line experience is recommended.

**Why it is worth a try:**
- 📚 **Glossary-driven** — a `.dic` dictionary keeps terminology consistent across a whole book and a whole series
- 🔨 **Extended dictionary work** — the dictionary can be verified against the book (`dict review`, `dict clean`), it is validated before every run, and it **automatically tries to fix the category and the gender** of every entry from the book itself (`DICT_AUTOFIX`)
- 🔁 **Dual-LLM, 5 stages** — one LLM translates, a second one reviews and polishes; every chunk passes INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- ☁️ **[OpenRouter](https://openrouter.ai)** or 💻 **local GPUs (16-24GB VRAM)** via llama.cpp, Ollama, LM Studio etc. and any OpenAI-compatible API (3-4M tokens per book), or any hosted API
- 💾 **Crash-proof** — progress checkpoints after every chunk, a resumed run continues where it stopped
- 🎓 For professional and non-professional translators alike — drafts and dictionaries included

## 🚀 Quick Start — a translated book in two runs

By default the models run in the cloud — no GPU and no local LLM server: [OpenRouter](https://openrouter.ai) serves [Gemma 4 26B A4B](https://openrouter.ai/google/gemma-4-26b-a4b-it), which translates, and [Qwen 3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b), which proofreads — the same models as the reference local setup.

1. **Install** (Python 3.11+; the dependencies come from `pyproject.toml`)
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   sudo apt install calibre pandoc     # EPUB/DOCX/PDF; macOS: brew install --cask calibre && brew install pandoc
   ```
2. **Key and book** — create a key at [openrouter.ai/keys](https://openrouter.ai/keys) and top up a few dollars. `cp env.cloud.sample .env`, put the key into `API_KEY_TRANSLATE` and `API_KEY_PROOFREAD`, the book into `FILE=books/mybook.epub`, the languages into `SOURCE_LANG` / `TARGET_LANG` and the country of your readers into `COUNTRY` (`México` or `España`, `Brasil` or `Portugal`: the translation follows its vocabulary and forms of address — required for Spanish, Portuguese, Chinese and the other languages used in many countries).
3. **First run — the dictionary.** `python app.py` finds the names and terms of the book (the spaCy model of the source language is downloaded on first use), translates them, writes `books/mybook_fr.dic` (`fr` — the code of `TARGET_LANG`: each target language has its own dictionary) and stops. Look it through: the translations, the categories, the genders of the characters — `books/mybook_fr.dictcheck.txt` lists what the book does not settle.
4. **Second run — the book.** `python app.py` picks up `books/mybook_fr.dic` and translates the whole book; the result is next to the source, `books/<title>_<lang>.epub`. Enjoy reading.

A 450-page novel costs about $1 (an estimate from the tokens of a real run; the OpenRouter activity page shows the exact cost). `env.cloud.sample` turns the models' thinking off and keeps to providers that support every parameter of the request (JSON mode).

**The way to a perfect book — the dictionary first.** The dictionary decides the quality more than anything else: every chunk takes its names, terms and genders from it, so every fix in it shows on every page. For the best result take the longer way:
1. After the first run, a fast draft that grows the dictionary: `FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` — the synopsis stage adds the names and coined terms of the whole book and fills in empty genders (existing lines are never rewritten); about 2.5x faster than a full run.
2. Check the dictionary: `python app.py dict clean books/mybook_fr.dic` and `python app.py dict review books/mybook.epub --dic books/mybook_fr.dic` (a cleaned / reviewed copy and a report next to it), then fix by hand what is left — the genders first.
3. Translate from scratch with the finished dictionary: `python app.py --fresh`.

**Local models instead of the cloud:** `env.sample` (llama.cpp, Ollama, LM Studio; 16–24 GB VRAM); Docker images — next section. **A draft only?** `FAST_TRANS=true`.

## 🪟 Windows (via WSL2)

The project runs on Linux, so on Windows 10 (version 2004 or newer) and Windows 11 it runs in WSL2 — a Linux inside Windows. The cloud models need no GPU, so this is the whole setup, with the [OpenRouter](https://openrouter.ai) configuration of the Quick Start.

1. **WSL2 with Ubuntu** — in PowerShell as administrator: `wsl --install -d Ubuntu-24.04`, restart when asked, open *Ubuntu 24.04* from the Start menu and create a Linux user name and password. (Ubuntu 24.04 ships Python 3.12; Ubuntu 22.04 has Python 3.10, too old.)
2. **Tools** — in the Ubuntu window:
   ```bash
   sudo apt update && sudo apt install -y git python3-venv python3-pip calibre pandoc
   ```
3. **The project** — in the Linux home folder, not under `/mnt/c` (files on the Windows disk are slow in WSL2):
   ```bash
   cd ~ && git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   ```
4. **OpenRouter key and config** — create a key at [openrouter.ai/keys](https://openrouter.ai/keys) and top up a few dollars. `cp env.cloud.sample .env && nano .env`: put the key into `API_KEY_TRANSLATE` and `API_KEY_PROOFREAD`, the book into `FILE=books/mybook.epub`, the languages into `SOURCE_LANG` / `TARGET_LANG` and the country of your readers into `COUNTRY`. Save with Ctrl+O, Enter, Ctrl+X. The OpenRouter lines are the defaults of `env.cloud.sample`, nothing else to change.
5. **The book** — copy it into WSL: `cp /mnt/c/Users/<your Windows name>/Downloads/mybook.epub books/`, or open `\\wsl$\Ubuntu-24.04\home\<linux user>\sunny-narrator\books` in Explorer and drag the file there.
6. **Two runs** — `python app.py` builds the dictionary and stops; review it; `python app.py` translates the book (steps 3–4 of the Quick Start). The result is next to the source in the same `books` folder, visible in Explorer at the same `\\wsl$` path.

Next time: open *Ubuntu 24.04*, `cd ~/sunny-narrator && source .venv/bin/activate`, `python app.py`. A long run needs the window open and the computer awake; an interrupted run continues from its checkpoint.

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

# 3. Run — first pass builds books/mybook_fr.dic, review it, run again to translate
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# CPU image: drop --gpus all and use ...sunny-narrator:main-cpu
```

Alternative with compose (config `.env` is read automatically): `docker compose run --rm sunny-narrator` (GPU) or `docker compose -f docker-compose.cpu.yml run --rm sunny-narrator`.

**Guides:** [docs/DOCKER.md](docs/DOCKER.md)

## 📋 Configuration

`env.sample` is a complete, documented reference: every parameter of the system is listed there with its description and default, and the end of the file has ready-made variants (two llama.cpp servers, one Ollama, English source, FB2 → EPUB, fast draft). Key options:

```bash
API_KEY_TRANSLATE=your-api-key-here     # any non-empty string for a local server
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # translate LLM (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # proofread LLM (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=en
TARGET_LANG=fr
COUNTRY=France
OUTPUT_FORMAT=fb2                       # fb2|epub for FB2/TXT; epub|docx|pdf for EPUB/DOCX/PDF
```

**All options:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Dictionary (the heart of the quality)

- The first run builds `book.dic` automatically: the spaCy model of the source language finds names; categories and genders are decided by the book itself, the LLM only translates.
- Before every translation the dictionary is **checked against the book** (no LLM): sure findings fix the category/gender for that run; the `.dic` itself is never silently changed — `<dic>.reviewed.dic` gets them.
- `PERSON` entries carry a gender into every stage prompt and are enforced by the GENDER stage; put races/species/coined words as `TERM`.
- Series-wide dictionary: `--build-series-dict`, then one `series.dic` for all volumes (`DICTIONARY=series.dic`).
- Standalone tools: `dict clean`, `dict review`, `dict extend`, `dict convert`, `audit`.

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
| **Sampling (temperatures, presence_penalty, thinking)** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Rechunking** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Resume after Crash** | [docs/RESUME.md](docs/RESUME.md) |
| **Logging** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker** | [docs/DOCKER.md](docs/DOCKER.md) |
| **Tested Languages** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |
| **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **For AI agents** | [AGENTS.md](AGENTS.md) |

## 🈶 CJK sources (Korean, Japanese, Chinese)

Direct translation from CJK into any language is supported out of the box: `ja`/`zh` models need `pip install -e ".[cjk]"` (Korean needs nothing extra); terms match as substrings, Korean particles are cut when writing the dictionary, and the learned length ratio absorbs the 2-4x text growth. **Full nuances:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 Changelog

Release history: [CHANGELOG.md](CHANGELOG.md)
