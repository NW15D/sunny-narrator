# Configuration Guide — Complete Parameter Reference

**Version:** 2.9  
**Updated:** 2026-10-10

---

## 📋 Overview

All settings are read from `.env` in the project root (see `src/config.py`).
Start from the bundled [`env.sample`](../env.sample): it is a complete working
configuration — **Gemma 4** translates, **Qwen 3.6** proofreads, both through an
OpenAI-compatible server — with every option documented inline and ready-made
variants at the end of the file.

```bash
cp env.sample .env
```

Minimal changes: the two API blocks (`API_KEY_*`, `API_BASE_*`, `MODEL_*`),
`FILE`, `SOURCE_LANG`, `TARGET_LANG`.

---

## 🔧 LLM APIs

Any OpenAI-compatible endpoint works: llama.cpp (`llama-server`), Ollama,
LM Studio, vLLM, hosted APIs. `MODEL_*` must be the model name exactly as the
server reports it (`GET <API_BASE>/models`). For a local server without
authentication any non-empty API key will do.

### Translate LLM — stage 1 (INITIAL) and 5 (SYNOPSIS)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_TRANSLATE` | — | API key |
| `API_BASE_TRANSLATE` | `http://localhost:11434/v1` | Base URL |
| `MODEL_TRANSLATE` | `Mistral` | Model name (reference setup: Gemma 4) |
| `TEMP_TRANSLATE` | `0.01` | Base temperature (fallback for `TEMP_INITIAL`) |
| `TIMEOUT_TRANSLATE` | `6000` | Request timeout, seconds |
| `NOTHINK_TRANSLATE` | `false` | Disable the model's thinking/reasoning mode |
| `S_PROMT_TRANSLATE` | `false` | `true` for models without system-prompt support (the system prompt is merged into the user message) |

### Proofread LLM — stages 2-4 (REFLECTION, IMPROVE, FINAL_EDIT)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_PROOFREAD` | — | API key |
| `API_BASE_PROOFREAD` | `https://api.openai.com/v1` | Base URL |
| `MODEL_PROOFREAD` | `tencent/Hunyuan-MT-7B` | Model name (reference setup: Qwen 3.6) |
| `TEMP_PROOFREAD` | `0.7` | Base temperature |
| `TIMEOUT_PROOFREAD` | `6000` | Request timeout, seconds |
| `NOTHINK_PROOFREAD` | `false` | Disable thinking mode |
| `S_PROMT_PROOFREAD` | `false` | Same as `S_PROMT_TRANSLATE` |

### Images LLM — cover (classic pipeline, optional)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_IMAGES` | — | Empty = the original cover is kept. When set, the cover is sent to the images model (**a paid call per book**) and replaced by the result, which is also saved as `<book>_<lang>_cover.<ext>` (`<lang>` — ISO code of `TARGET_LANG`, e.g. `ru`) |
| `API_BASE_IMAGES` | — | Base URL |
| `MODEL_IMAGES` | `gpt-image-1.5` | Model name |
| `TIMEOUT_IMAGES` | `600` | Request timeout, seconds |

### Stage temperatures

| Parameter | Default | Stage |
|-----------|---------|-------|
| `TEMP_INITIAL` | `TEMP_TRANSLATE` | 1 — initial translation |
| `TEMP_REFLECTION` | `0.4` | 2 — quality review |
| `TEMP_IMPROVE` | `0.4` | 3 — apply review suggestions |
| `TEMP_FINAL_EDIT` | `0.15` | 4 — final proofreading |
| `TEMP_SYNOPSIS` | `0.15` | 5 — synopsis for the next chunk |
| `TEMP_GENDER` | `0.05` | GENDER — fix of the gender errors found |

**Details:** [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md)

### JSON mode

| Parameter | Default | Description |
|-----------|---------|-------------|
| `JSON_MODE` | `false` | Structured JSON input/output for all stages (**recommended: `true`**) |
| `DISABLE_JSON_MODE_TRANSLATE` / `DISABLE_JSON_MODE_PROOFREAD` | `true` | Per-role switches, used only when `JSON_MODE` is not `true` |

**Details:** [JSON_MODE_ANALYSIS.md](JSON_MODE_ANALYSIS.md)

---

## 🌍 Book and languages

| Parameter | Default | Description |
|-----------|---------|-------------|
| `FILE` | `books/ExampleBook.fb2` | The book. `.fb2`/`.txt` → classic pipeline, `.epub`/`.docx`/`.pdf` → Calibre pipeline |
| `SOURCE_LANG` | `english` | Full name or ISO code (`korean`/`ko`, `english`/`en`, ...). Also selects the spaCy model and the CJK adaptations. Verified languages: [LANGUAGES.md](LANGUAGES.md) |
| `TARGET_LANG` | `russian` | Full name or ISO code. Verified languages: [LANGUAGES.md](LANGUAGES.md) |
| `COUNTRY` | by `TARGET_LANG` | Country for localization context in prompts; empty = derived from the target language (`ru` → Россия, `tr` → Türkiye, `de` → Deutschland, …; a language without one country → `<Language>-speaking countries`) |

---

## ⚡ Processing

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_LEN_CHUNK` | `8192` | Chunk size in source characters. The classic pipeline cuts only between blocks (paragraphs, poems between stanzas), so a single larger block stays whole |
| `LENGTH_CHECK_THRESHOLD` | `20` | Allowed deviation (%) from the expected translation length before a chunk is split and retranslated |
| `FAST_TRANS` | `false` | Skip stages 2-4 (both pipelines; `--fast-mode` turns it on too); the GENDER stage still runs |
| `GENDER_CHECK` | `fix` | GENDER stage, both modes: a sentence where a dictionary character (gender `he`/`she`) is the subject and the verb or adjective has the other gender is found without an LLM (spaCy model of `TARGET_LANG` needed) and sent to the LLM for a fix (`fix`, the LLM is `GENDER_LLM`), only logged (`warn`), or not checked (`off`) |
| `GENDER_LLM` | `auto` | LLM of the GENDER call: `auto` — proofread, with `FAST_TRANS` too, unless it is another model on the same local server as the translate LLM (one Ollama would swap the models every chunk), then translate; `translate` — always translate (`FAST_TRANS` with only the translate model loaded); `proofread` — always proofread |

**Details:** [RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md), [FAST_TRANS.md](FAST_TRANS.md)

---

## 📎 Dictionary and NER

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NER` | `true` | Build the dictionary from named entities on the first run (every format; the run then stops for review). Off: an empty template is created and terms are matched without spaCy. `--build-dict` runs NER regardless |
| `NERMODEL` | by `SOURCE_LANG` | spaCy model; empty = chosen from `SOURCE_LANG` and downloaded automatically (`en` → `en_core_web_lg`, `ko` → `ko_core_news_lg`, ...; full map in `src/config.py`); a language without its own spaCy pipeline (Turkish, Hungarian, Arabic, …) → multilingual `xx_ent_wiki_sm` |
| `DICT_FREQUENT_WORDS` | `false` | Also add frequent ordinary words (not named entities) to a new dictionary. Off: they fill the `.dic` with translations of common vocabulary. Per run for `--build-dict`/`--build-series-dict`: `--frequent-words` |
| `DICT_CHECK` | `true` | Check the dictionary against the source book before a translation (categories by NER, genders by pronouns; no LLM). See [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md#dictionary-check-before-a-translation) |
| `DICT_AUTOFIX` | `true` | Apply the sure findings of that check for the run (the `.dic` is not changed). `false` / `--no-autofix`: a dictionary contradicting the book stops the run, unless `--force` |
| `DICT_AUTO_SAVE` | `false` | Write the names and coined terms the synopsis stage finds while translating into the `.dic`. Off: they join the in-memory dictionary for the rest of the run (and its resume, via the checkpoint), but the file stays as you reviewed it. A candidate already covered by the dictionary is never added — neither another case or inflected form of an entry (`Jain nodes`, `Gabbleducks`) nor a phrase containing a known term (`Jain node`, `Jain-tech` when `Jain` is there). A hyphen, a space or no separator make different entries (`gabble-duck` is not `gabbleduck`). Works the same with `FAST_TRANS=on`: the synopsis stage is kept, so the dictionary grows in fast mode too (see [FAST_TRANS.md](FAST_TRANS.md)) |
| `DICTIONARY` | empty | Explicit path to the `.dic` file instead of `<book>.dic` next to the book. CLI: `--dictionary <path>` (wins over `.env`). Both pipelines |

**Details:** [NER_GUIDE.md](NER_GUIDE.md), [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md)

---

## 📤 Output

| Parameter | Default | Description |
|-----------|---------|-------------|
| `OUTPUT_FORMAT` | `fb2` | FB2/TXT input: `fb2` or `epub`. EPUB/DOCX/PDF input: `epub`, `docx` or `pdf` (`fb2` there means `epub`). CLI: `--output-format` (wins over `.env`) |
| `FB2_AUTO_REPAIR` | `true` | Classic pipeline: if the finished FB2 fails schema validation, rebalance its tags where they break. The repair is kept only if the book text is unchanged, the result is well-formed and the error count drops |

The result is written next to the source file with a language marker in its
name — the ISO code of `TARGET_LANG` (`russian` and `ru` both give `ru`), e.g.
`books/Book_ru_1530-2909.fb2` (classic) or `books/Title_ru.epub` (Calibre).

---

## 📚 Calibre pipeline (EPUB/DOCX/PDF input)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PANDOC_BATCH_CHARS` | `200000` | Markdown → HTML conversion batch size |
| `PANDOC_TIMEOUT` | `900` | Seconds before a pandoc batch is killed |
| `CALIBRE_TIMEOUT` | `1800` | Seconds before `ebook-convert` is killed |
| `MAX_FAILED_CHUNK_RATIO` | `0.0` | Share of failed chunks allowed before the pipeline aborts |

---

## 🔍 Logging

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEBUG` | `off` | Detailed console log (length checks, dictionary matching, synopsis) |
| `DEBUG_HTTP` | `off` | With `DEBUG` on: also raw HTTP traces of the LLM clients |
| `LLM_LOGGING` | `false` | Every LLM call as a JSON line in `LLM_LOGGING_DIR/llm_calls_YYYY-MM-DD.log` |
| `LLM_LOGGING_DIR` | `logs` | Directory for the LLM call log |

**Details:** [LOGGING.md](LOGGING.md)

---

## 🕰️ Legacy names

Older `.env` files keep working: these names are read when the new one is not set.

| New name | Old name |
|----------|----------|
| `API_KEY_TRANSLATE`, `API_BASE_TRANSLATE`, `MODEL_TRANSLATE`, `TEMP_TRANSLATE`, `TIMEOUT_TRANSLATE`, `S_PROMT_TRANSLATE` | `API_KEY`, `API_BASE`, `MODEL`, `TEMP`, `TIMEOUT`, `S_PROMT` |
| `API_KEY_PROOFREAD`, `API_BASE_PROOFREAD`, `MODEL_PROOFREAD`, `TEMP_PROOFREAD`, `TIMEOUT_PROOFREAD`, `S_PROMT_PROOFREAD` | `API_KEY2`, `API_BASE2`, `MODEL2`, `TEMP2`, `TIMEOUT2`, `S_PROMT2` |
| `API_KEY_IMAGES`, `API_BASE_IMAGES`, `MODEL_IMAGES`, `TIMEOUT_IMAGES` | `API_KEY3`, `API_BASE3`, `MODEL3`, `TIMEOUT3` |

Removed in 2.5 (ignored if still present): `CONCURRENT_LIMIT`, `COVER_PROMPT`,
`S_PROMT_IMAGES`/`S_PROMT3`, `TEMP_IMAGES`/`TEMP3`, `SHORT`, `EXAMPLE`.

---

## ✅ Checking the configuration

```bash
python3 -c "from src.config import Config; c = Config(); print(c.model_translate, c.model_proofread, c.output_format, c.ner_opt)"
```

---

## 📚 Related documentation

- [INSTALLATION.md](INSTALLATION.md) — installation
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-stage pipeline
- [RESUME.md](RESUME.md) — resume after a crash
- [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md), [GPU_DOCKER.md](GPU_DOCKER.md) — Docker
