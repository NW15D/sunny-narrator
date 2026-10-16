# Sunny Narrator

**English** | [Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — translate EPUB, PDF, TXT, FB2 and DOCX books into many languages" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Version:** 2.9.2  
**Glossary-Driven AI Book Translator** for FB2/TXT/EPUB/DOCX/PDF — an LLM-powered fiction book translator with dual-LLM translation and 5-stage quality control.

🖥️ **Console app (CLI)** — no graphical interface; basic command-line experience is recommended.

**Designed for:**
- 📚 Glossary-driven translation of book series (consistent terminology across volumes)
- 🔨 Dictionary creation for book and series translations
- 💻 Local GPUs (16-24GB VRAM) via llama.cpp, Ollama, LM Studio etc. and any OpenAI-compatible API (3-4M tokens per book)
- ☁️ Online translation services via API
- 🎓 Professional and non-professional translators alike — for drafting book translations and building dictionaries

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
5. **Build the dictionary** — `python app.py` creates `book.dic` next to the book (the spaCy model for the source language is downloaded automatically). The run stops here so you can review it (all formats)
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

# Any format: the first run builds the dictionary, the second one translates
FILE=books/mybook.fb2 python app.py
```

**Full documentation:** [docs/](docs/)

---

## 📋 Configuration

Copy the bundled `env.sample` to `.env`. It is a complete, working configuration: **Gemma 4** translates and **Qwen 3.6** proofreads, both through an OpenAI-compatible server (llama.cpp, Ollama, LM Studio, vLLM or a hosted API). Every option is documented inline, and the end of the file has ready-made variants: two llama.cpp servers, one Ollama server, an English source, FB2 → EPUB and a fast draft.

```bash
cp env.sample .env
```

Then adjust at least these keys:

```bash
# Translate LLM — Gemma 4
API_KEY_TRANSLATE=your-api-key-here        # any non-empty string for a local server
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B                 # name as your server reports it

# Proofread LLM — Qwen 3.6
API_KEY_PROOFREAD=your-api-key-here
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B

# Book and languages
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru

# Output: fb2 or epub for FB2/TXT; epub, docx or pdf for EPUB/DOCX/PDF
OUTPUT_FORMAT=fb2
```

**All options:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS Mode

**Use `FAST_TRANS=true` (or `--fast-mode`) for:**
- ✅ Draft translation
- ✅ Technical docs
- ❌ NOT for final publication or literary translation

**Speed:** ~2.5x faster (2 stages instead of 5)

**💡 Trick — a good dictionary after the first fast pass:** run the fast translation with `DICT_AUTO_SAVE=true`. The synopsis stage still runs in fast mode, so new names and terms are appended to the `.dic` (only those the dictionary does not cover yet; an existing entry may get its empty gender filled in). Review and fix the dictionary, then translate the book a second time with `FAST_TRANS=false` and `--fresh` — a quality translation with consistent terminology. `--fresh` keeps the chunks and terms of an interrupted fast pass from coming back. Works for every format (FB2/TXT and DOCX/EPUB/PDF).

**Details:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📏 Chunk Length Calibration

After each chunk is translated, its length is checked against an expected source→target ratio to catch truncated or bloated output. Instead of a fixed threshold, the ratio is calibrated automatically per book: the first 3 accepted chunks are only checked for gross failures (×0.25 … ×5), then the expected ratio becomes the median of accepted chunks so far.

**Details:** [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md)

---

## 📎 Vocabulary

Dictionary file (`*.dic`) ensures terminology consistency:

```dic
# Format: source = target, category, gender, notes
Alice = Алиса, PERSON, she, Main character
```

- **Created automatically** on the first run (or with `--build-dict`): the spaCy model of the source language finds the names; the categories and genders are decided by the book itself (the majority of NER labels, the pronouns, forms of address like *Miss*/*Mr.*), the LLM only translates. An unsure gender stays empty, and the run stops so you can review the new `.dic`. Frequent ordinary words are added only with `DICT_FREQUENT_WORDS=true` (or `--frequent-words` for `--build-dict`/`--build-series-dict`).
- **Checked against the book before every translation** (no LLM): sure findings — an empty gender, a gender or category the book contradicts — apply to that run only; the `.dic` is not changed, `<dic>.reviewed.dic` gets them. `--no-autofix` translates by the `.dic` as it is (with `DICT_FORCE=false` a contradiction stops the run); the report is `<book>.dictcheck.txt`.
- **The category changes how an entry is translated.** Only `PERSON` has behaviour of its own: its gender goes into the `<characters>` block of every stage and is enforced by the GENDER stage. `LOC`, `ORG` and `TERM` are plain glossary entries without a gender. So put a named character (even a non-human one) as `PERSON` with a gender, and a race, species, title, technology or coined word as `TERM` — a race as `PERSON` would get a gender and be made to agree with it. Places are `LOC`, organizations `ORG`. The category also decides what the check before a translation may change (see `docs/DICTIONARY_FORMAT.md`).
- **Character genders** (`he`, `she`, `it`, `they`): every stage gets them written the target language's way (`Вашти — она (сказала)`), and the GENDER stage fixes sentences that contradict the dictionary. A gender in the file is never overwritten by a run; the synopsis fills in only empty ones, when two chunks agree.
- **Coined words:** besides characters, the synopsis stage reports invented words with no ordinary translation (`spidergun`); they are added as `TERM`. Words the spaCy model already knows are dropped.
- **No duplicates:** a candidate the dictionary already covers is not added — another case or inflected form of an entry (`Jain nodes` = `Jain node`, `Gabbleducks` = `gabbleduck`; a name only by inflection: `Jains` = `Jain`, but `Marie` ≠ `Mary`) or a phrase containing a known term (`Jain node`, `Jain-tech` when `Jain` is there). A hyphen, a space or no separator make different entries (`gabble-duck` ≠ `gabbleduck`); an ALL-CAPS acronym matches only itself (`ECS` ≠ `EC`).
- **Where found entries go:** new names and terms join the in-memory dictionary at once — the following chunks of the run use them, and a resumed run restores them from the checkpoint. They are written to the `.dic` only with `DICT_AUTO_SAVE=true` (default `false`: the reviewed dictionary stays as it is).
- **Term matching:** the same for every format — only the dictionary terms found in a chunk go into its prompt. Inflected forms are found (`spidergun` → `spiderguns`, `wolf` → `wolves`), Chinese/Japanese/Korean terms are matched as substrings, and a term never matches inside another word (`Ann` / `Annoying`).
- **Multi-word terms first:** a term of more words beats the shorter ones it contains (`Mad Hatter` over `Hatter`), then the longer one wins. A shorter term that occurs only inside a longer one is not put into the prompt, so the model never gets two translations of one phrase.
- **Terms are substituted before translation:** the translations of the dictionary terms found in a chunk are put into the source text before the first stage, so the model cannot skip them (the later stages see the original). Markup, links and URLs are never touched; a lowercase term matches in any case, a name as written or in ALL CAPS.
- **Other target language:** `python app.py dict convert books/MyBook.dic fr es zh` converts a finished dictionary to other languages (`MyBook_fr.dic`, …) using the existing translation as a hint.
- **Explicit dictionary path:** by default the dictionary is looked up next to the book (`books/MyBook.fb2` → `books/MyBook.dic`). Set `DICTIONARY=path/to/file.dic` in `.env` or pass `--dictionary path/to/file.dic` (the CLI flag wins) to use another file, e.g. a shared series dictionary. Works in both pipelines; a missing file is created at that path (its directory must exist).

**Format guide:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

### Working with dictionaries

| Task | Command / step |
|---|---|
| New book, no dictionary | `python app.py` (or `python app.py --build-dict books/MyBook.epub`) → `books/MyBook.dic` + `books/MyBook.dictcheck.txt` → fill in the empty genders you know → run again |
| Translate with a dictionary | `python app.py` — the check runs first; read `<book>.dictcheck.txt`, take `<dic>.reviewed.dic` if you agree |
| Strict mode | `python app.py --no-autofix` — by the `.dic` as it is; `DICT_FORCE=false` — stops on a contradiction (exit code 2) |
| Series of books | `python app.py --build-series-dict books/series/ --series-dict-output series.dic`, then each book with `--dictionary series.dic`; a run never changes `series.dic`, each book gets `series.<book>.reviewed.dic` |
| Clean a dictionary | `python app.py dict clean books/MyBook.dic` → `MyBook.clean.dic` + report (duplicates, gender spellings, ordinary words) |
| Check against the book without translating | `python app.py dict review books/MyBook.epub --dic books/MyBook.dic` → `MyBook.reviewed.dic` + report |
| Another target language | `python app.py dict convert books/MyBook.dic fr es zh` |
| Check a finished translation | `python app.py audit books/MyBook_ru.epub --dic books/MyBook_ru.dic --lang russian` |

**Languages.** The dictionary is built and checked with the spaCy model of the **source** language (`NERMODEL`, chosen by `SOURCE_LANG`): `python -m spacy download en_core_web_lg` (English), `ru_core_news_lg`, `de_core_news_lg`, `fr_core_news_lg`, `es_core_news_lg`, `it_core_news_lg`, `pt_core_news_lg`, `pl_core_news_lg`, `uk_core_news_lg`, `ko_core_news_lg`, `ja_core_news_lg`, `zh_core_web_lg`; any other language uses `xx_ent_wiki_sm` (names only, no genders from pronouns). The gender check of the **translation** needs the model of the target language (`ru_core_news_sm`, `pl_core_news_sm`, `fr_core_news_sm`, …). Chinese, Japanese and Korean pronoun genders are read by their form; a book in a language without gendered pronouns (Turkish, Finnish, Hungarian) gives no genders — set them by hand.

### Before translating (or retranslating) a series

1. Back up the dictionary: `cp series.dic series.dic.bak`.
2. Clean it: `python app.py dict clean series.dic` — read the report, take over what you agree with.
3. Check it against every book, each into its own file: `python app.py dict review book1.epub --dic series.dic -o series.book1.reviewed.dic` (the same for book2, …). Take over what the books agree on; decide the rest by hand — the `gender conflict` and `gender not sure` sections first.
4. Fix by hand what no tool can: a female character whose name is a masculine noun in the target language (`Client` → `Клиентка`?), a species or a title marked PERSON (→ `TERM`), a gender that jumps between `it`/`he`/`they`.
5. Translate the books in series order with `DICTIONARY=series.dic`, `DICT_AUTO_SAVE=false`, `--fresh`. Before the first chunk the dictionary is checked against that book; the sure fixes apply to that run only.
6. After each book, before the next one: read the run report (*The translation disagrees with the dictionary*, *Genders filled in from the synopsis*, *Words in two alphabets*), `<book>.dictcheck.txt` and `series.<book>.reviewed.dic`, and take over what is right into `series.dic`. Compare with an older translation: `python app.py audit … --compare …`.

---

## 🈶 CJK Languages (Korean, Japanese, Chinese)

Books can be translated directly from CJK languages into any language, with a dictionary:

- **NER:** `ko_core_news_lg` uses its own KLUE label scheme (`PS`/`LC`/`OG`) — it is recognized and normalized to `PERSON`/`LOC`/`ORG`.
- **Dictionary matching:** CJK terms are found as substrings — there are no spaces between words, and Korean particles are glued to nouns (`철수는`).
- **Models:** `python -m spacy download ko_core_news_lg` (nothing extra), `ja_core_news_lg` and `zh_core_web_lg` need their tokenizers: `pip install -e ".[cjk]"`.
- **Korean particles:** entities are written to the dictionary without the glued particle (`철수는` → `철수`, `서울에서` → `서울`), so a term matches every form of the word. Because of the substring search a short name also matches inside a longer one (`철수` in `김철수`) — check such terms in the generated `.dic`.
- **Priority:** the longest term wins (`魔王城` over `魔王`); a Latin term inside CJK text (`ABC社`, full-width `ＡＢＣ` too) is substituted as a word of its own.
- **Frequent words** (only with `DICT_FREQUENT_WORDS=true`): minimum word length is 2 characters instead of 5 (a CJK word is usually 1-3 characters).
- **Length check:** a CJK text grows 2-4x in characters when translated into alphabetic languages. The expected ratio is learned from the book itself — the median of accepted chunks; the first 3 chunks are only checked for gross failures (×0.25 … ×5).

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

---

## 🌍 Tested Languages

Any language the LLM can write works as a target; the dictionary code is language-aware. Verified so far:

| | Languages |
|---|---|
| **Real book translations** | English → Russian, Korean → Russian |
| **Source, real spaCy model** (NER, term forms, article/particle cleanup) | English, Korean, Japanese, Chinese, Russian, German, French, Spanish, Portuguese, Italian |
| **Source, limited** | Turkish (multilingual NER; a term is found only in the form written in the `.dic`) |
| **Target, automated tests** | Russian, Turkish (all five stages with a faked LLM), German, Chinese |

**Details and limits:** [docs/LANGUAGES.md](docs/LANGUAGES.md)

---

## 📖 Glossary-Driven Translation (Series of Books)

Create a unified dictionary for a series of books to ensure consistent terminology across all volumes.

### Build Series Dictionary

```bash
# Basic usage
python app.py --build-series-dict books/ --series-dict-output series.dic

# With custom thresholds
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --frequent-words --min-count-word 5
```

**Parameters:**
- `--build-series-dict` — Path to folder containing FB2/EPUB/TXT books
- `--series-dict-output` — Output dictionary file (default: `series.dic`)
- `--min-count-ner` — Minimum occurrences for NER entities (default: 2)
- `--frequent-words` — Also add frequent ordinary words, not only named entities (default: off, `DICT_FREQUENT_WORDS`)
- `--min-count-word` — Minimum occurrences for common words with `--frequent-words` (default: 5)

A dictionary for a single book can be built with `--build-dict path/to/book`.

**Workflow:**
1. Find all book files in folder
2. Extract text from each book
3. Run NER: one entry per entity (forms grouped by lemma, the category most mentions got)
4. Aggregate counts across all books
5. Filter by threshold criteria
6. Translate the terms via the proofread LLM (it only translates; genders are set by the check before each book's translation)
7. Save unified `.dic` file

**Output:** a regular `.dic` file (`source = target, category, gender, notes`). Proper names keep their capitalization and all their words (`John Smith`).

---

## 💾 Resume after Crash

Automatic progress saving after each chunk:

```bash
# Interrupted at 50%
python app.py  # Ctrl+C

# Resume automatically
python app.py  # ✓ Resuming from chunk 51/100
```

`--fresh` ignores the checkpoint and starts from scratch (both pipelines).

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

**Pre-built images** ([GitHub Container Registry](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator), built from `Dockerfile` / `Dockerfile.cpu` and tested on every push to `main`; both include Calibre and pandoc):
```bash
docker pull ghcr.io/nw15d/sunny-narrator:main       # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu   # CPU
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

**FB2 → EPUB:** `FILE=books/mybook.fb2 python app.py --output-format epub` (or `OUTPUT_FORMAT=epub` in `.env`). The classic pipeline translates the FB2 and builds the EPUB straight from it: nested table of contents, footnotes, cover, images, poems and epigraphs.

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
| **Tested Languages** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |

---

## 📝 Changelog

Release history: [CHANGELOG.md](CHANGELOG.md)
