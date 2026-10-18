# Instructions for AI agents

For coding agents (Claude Code, Codex / ChatGPT, Cursor, Copilot and the like)
asked to install Sunny Narrator, translate a book with it, or change its code.
Humans: the same steps are in the [README](README.md) Quick Start.

Sunny Narrator is a command-line book translator: FB2/TXT/EPUB/DOCX/PDF in, the
translated book next to the source out. Two LLMs over an OpenAI-compatible API
(one translates, one proofreads), a `.dic` dictionary of names and terms that
keeps a book and a series consistent.

## Install and translate a book for a user

### Ask the user first

These are the user's decisions; do not guess them:

1. **The LLM provider and the key.** By default cloud models: OpenRouter
   (https://openrouter.ai), or ProxyAPI (https://proxyapi.ru, rubles, from
   Russia). Local models (llama.cpp, Ollama, LM Studio, 16–24 GB VRAM) use
   `env.sample` instead. Let the user type the key into `.env` themselves;
   never print it, log it or commit it.
2. **The book** (path), **the source and the target language.**
3. **Spending.** A run costs money (about $1 for a 450-page novel with the
   cloud sample; the demo book about $0.3). Start a translation only when the
   user asked for it.

### Install

Python 3.11+. The dependencies come from `pyproject.toml` only (there is no
`requirements.txt`); no GPU and no torch are needed.

```bash
git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
python3 -m venv .venv && . .venv/bin/activate     # Debian/Ubuntu without venv: apt install python3-venv
pip install -e .
sudo apt install calibre pandoc                    # EPUB/DOCX/PDF input; macOS: brew install --cask calibre && brew install pandoc
```

FB2 and TXT books need neither Calibre nor pandoc. The spaCy models (the
source language, about 400 MB for English; the target language for the
gender check) are downloaded on first use.

Check: `sunny-narrator --help` (or `python app.py --help`) prints the options.

### Configure

```bash
cp env.cloud.sample .env
```

In `.env`:
- `API_KEY_TRANSLATE`, `API_KEY_PROOFREAD` — the user's key (the same key twice);
- ProxyAPI instead of OpenRouter: uncomment the `PROXYAPI` block at the end;
- `FILE=books/<book>.epub`, `SOURCE_LANG`, `TARGET_LANG` (names or ISO codes:
  `en`, `ru`, `english`, …);
- the demo books: `books/eternal-moment.pg.epub`,
  `books/forster-short-fiction.se.epub` (English, public domain). When the
  repository has their dictionary for the target language
  (`books/eternal-moment.pg_ru.dic`), the first run translates at once.

Every option is documented in `env.sample` and
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Run

Run from the repository root, with the venv active.

1. **First run — the dictionary.** `python app.py` finds the names and terms
   of the book, translates them, writes `books/<book>_<lang>.dic` (`<lang>` —
   the code of `TARGET_LANG`, one dictionary per target language) and stops with
   "Dictionary created". Not an error: show the user the dictionary and
   `books/<book>.dictcheck.txt` (what the book does not settle — genders of
   characters first) and let them correct it. Do not edit the dictionary for
   them without asking.
2. **Second run — the book.** `python app.py` picks the dictionary up by that
   name and translates the whole book; the
   result is next to the source, `books/<title>_<lang>.epub`.

A run is long (tens of minutes for the demo book, hours for a novel): start it
in the background or with a generous timeout, and keep the log:
`mkdir -p logs && python app.py 2>&1 | tee logs/run.log`. An interrupted run resumes from its
checkpoint when started again; `--fresh` starts over.

For the best quality (the user's call, it costs a second pass): a fast draft
grows the dictionary — `FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` —
then `python app.py dict clean books/<book>_<lang>.dic` and
`python app.py dict review books/<book>.epub --dic books/<book>_<lang>.dic`, the user
reviews, then `python app.py --fresh`.

### Read the result

- **Exit codes:** `0` done (or the dictionary created and the run stopped for
  review); `1` a failure (the message and a traceback); `2` the dictionary
  contradicts the book and `DICT_FORCE=false`; `3` the API refused the request
  (the message names the variable to check).
- **The end of the log** has a `TRANSLATION METRICS REPORT`: failed chunks,
  tokens, words in two alphabets, gender errors found and fixed, the
  characters whose gender in the translation disagrees with the dictionary.
  Report these to the user; failed chunks are kept untranslated.
- **Every LLM call** (prompts, answers, tokens, time) is in
  `logs/llm_calls_YYYY-MM-DD.log` with `LLM_LOGGING=true` (on in the cloud
  sample).

### When it fails

| Symptom | Cause and fix |
|---|---|
| exit 3, `401` / `AuthenticationError` | wrong or empty key: `API_KEY_*` |
| exit 3, `403 Access denied by security policy` | OpenRouter does not serve this network: use ProxyAPI (or another network) |
| exit 3, `404` / `NotFoundError` | wrong model name or base URL: `MODEL_*`, `API_BASE_*` |
| `Calibre (ebook-convert) is not installed` | `apt install calibre` (EPUB/DOCX/PDF only) |
| `spaCy model … could not be downloaded` | offline: `python -m spacy download <model>` when online |
| `pip` fails on a source build | use Python 3.11–3.13 (wheels exist for them) |

More: [docs/INSTALLATION.md](docs/INSTALLATION.md),
[docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md),
[docs/RESUME.md](docs/RESUME.md), [docs/LOGGING.md](docs/LOGGING.md).

## Change the code

Read [CONTRIBUTING.md](CONTRIBUTING.md) (Development) first. In short:

```bash
pip install -e ".[dev]"
API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test python -m pytest -q
ruff check src tests
```

- The tests never call an LLM and never download spaCy models; all three API
  keys must be set to any string (the clients are created at import).
- Two pipelines chosen by the input format: FB2/TXT — `app.py`; DOCX/EPUB/PDF
  — `src/calibre_pipeline.py`. The translation core is `src/utils.py`, the
  dictionary `src/vocabulary_manager.py` (the only implementation), the
  prompts `src/prompts.json`, the commands besides a translation
  `src/commands.py` (`app.py dict …`, `audit`, `eval`).
- Rules: dependencies only in `pyproject.toml`; a new tool is an `app.py`
  subcommand, not a script; every change comes with a test
  (`tests/test_<feature>.py`); a prompt change is measured with `app.py eval`
  before and after; Conventional Commits.
- Never commit keys, `.env`, local network addresses, copyrighted books, or
  what a run leaves next to a book (`<book>_images/`, `*.checkpoint.json`,
  `*.dictcheck.*` — they are in `.gitignore`).
