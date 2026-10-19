# Configuration Guide — Complete Parameter Reference

## 📋 Overview

All settings are read from `.env` in the project root (see `src/config.py`);
an environment variable of the same name wins over `.env`. Two starting points:

- [`env.cloud.sample`](../env.cloud.sample) — cloud models (OpenRouter, or
  ProxyAPI from Russia): only the keys and the book need to be filled in;
- [`env.sample`](../env.sample) — every option documented inline, set up for
  your own OpenAI-compatible servers, with ready-made variants at the end.

Both use the reference pair: **Gemma 4 26B A4B** translates, **Qwen 3.6 35B
A3B** proofreads. The defaults in the tables below are the code's own, used
when a variable is not set at all — the samples set the important ones.

---

## 🔧 LLM APIs

Any OpenAI-compatible endpoint works: llama.cpp (`llama-server`), Ollama,
LM Studio, vLLM, hosted APIs. `MODEL_*` must be the model name exactly as the
server reports it (`GET <API_BASE>/models`). For a local server without
authentication any non-empty API key will do.

### Translate LLM — INITIAL and SYNOPSIS

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_TRANSLATE` | — | API key |
| `API_BASE_TRANSLATE` | `http://localhost:11434/v1` | Base URL |
| `MODEL_TRANSLATE` | `Mistral` | Model name as the server reports it; reference: Gemma 4 (`google/gemma-4-26b-a4b-it` in the cloud) |
| `TEMP_TRANSLATE` | `0.01` | Base temperature (fallback for `TEMP_INITIAL`) |
| `TIMEOUT_TRANSLATE` | `6000` | Request timeout, seconds |
| `NOTHINK_TRANSLATE` | `true` | Thinking/reasoning off: `chat_template_kwargs.enable_thinking=false` (llama.cpp) and `reasoning.effort=none` (OpenRouter, ProxyAPI) in every request; `false` lets the model think (slower, paid tokens) |
| `EXTRA_BODY_TRANSLATE` | — | A JSON object added to every request body, e.g. the OpenRouter provider choice `{"provider": {"require_parameters": true}}` (only providers that support every parameter of the request) (see `env.cloud.sample`) |
| `S_PROMT_TRANSLATE` | `false` | `true` for models without system-prompt support (the system prompt is merged into the user message) |

### Proofread LLM — REFLECTION, IMPROVE, FINAL_EDIT, GENDER, dictionary and metadata translation

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_PROOFREAD` | — | API key |
| `API_BASE_PROOFREAD` | `https://api.openai.com/v1` | Base URL |
| `MODEL_PROOFREAD` | `tencent/Hunyuan-MT-7B` | Model name as the server reports it; reference: Qwen 3.6 (`qwen/qwen3.6-35b-a3b` in the cloud) |
| `TEMP_PROOFREAD` | `0.7` | Base temperature |
| `TIMEOUT_PROOFREAD` | `6000` | Request timeout, seconds |
| `NOTHINK_PROOFREAD` | `true` | Same as `NOTHINK_TRANSLATE`. **Reasoning proofread model** (DeepSeek-R1, QwQ, gpt-oss): set `false`. Such a model thinks whatever it is told, and its thinking uses the same `max_tokens`; with `true` the REFLECTION call gets only about 1-3 thousand tokens and is cut off by it, chunk after chunk; with `false` that cap is off (`MAX_TOKENS_PER_CHUNK`) |
| `EXTRA_BODY_PROOFREAD` | — | Same as `EXTRA_BODY_TRANSLATE` |
| `S_PROMT_PROOFREAD` | `false` | Same as `S_PROMT_TRANSLATE` |

### Images LLM — cover (classic pipeline, optional)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_KEY_IMAGES` | — | Empty = the original cover is kept. When set, the cover is sent to the images model (**a paid call per book**) and replaced by the result, which is also saved as `<book>_<lang>_cover.<ext>` (`<lang>` — ISO code of `TARGET_LANG`, e.g. `ru`) |
| `API_BASE_IMAGES` | — | Base URL |
| `MODEL_IMAGES` | `gpt-image-1.5` | Model name |
| `TIMEOUT_IMAGES` | `600` | Request timeout, seconds |

### Sampling

| Parameter | Default | Stage |
|-----------|---------|-------|
| `TEMP_INITIAL` | `TEMP_TRANSLATE` | 1 — initial translation |
| `TEMP_REFLECTION` | `0.4` | 2 — quality review |
| `TEMP_IMPROVE` | `0.4` | 3 — apply review suggestions |
| `TEMP_FINAL_EDIT` | `0.15` | 4 — final proofreading |
| `TEMP_SYNOPSIS` | `0.15` | 5 — synopsis for the next chunk |
| `TEMP_GENDER` | `0.05` | GENDER — fix of the gender errors found |
| `PRESENCE_PENALTY_TRANSLATE` | `0` | presence_penalty of the translate LLM's requests |
| `PRESENCE_PENALTY_PROOFREAD` | `0` | presence_penalty of the proofread LLM's requests |
| `PRESENCE_PENALTY_REFLECTION` | `1.5` | presence_penalty of REFLECTION: without it the list of fixes repeats |

**Details:** [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md)

### JSON mode

| Parameter | Default | Description |
|-----------|---------|-------------|
| `JSON_MODE` | `true` | Structured JSON input/output for the text stages; `false` — the text prompts |
| `DISABLE_JSON_MODE_TRANSLATE` / `DISABLE_JSON_MODE_PROOFREAD` | `true` | Per-role switches, used only when `JSON_MODE=false` |

**Details:** [PROMPTS_GUIDE.md](PROMPTS_GUIDE.md#json-mode)

---

## 🌍 Book and languages

| Parameter | Default | Description |
|-----------|---------|-------------|
| `FILE` | `books/ExampleBook.fb2` (not in the repository: set it) | The book. `.fb2`/`.txt` → classic pipeline, `.epub`/`.docx`/`.pdf` → Calibre pipeline. The demo books: `books/eternal-moment.pg.epub`, `books/forster-short-fiction.se.epub` |
| `SOURCE_LANG` | `english` | Full name or ISO code (`korean`/`ko`, `english`/`en`, ...). Also selects the spaCy model and the CJK adaptations. Verified languages: [LANGUAGES.md](LANGUAGES.md) |
| `TARGET_LANG` | `french` | Full name or ISO code. Verified languages: [LANGUAGES.md](LANGUAGES.md) |
| `COUNTRY` | by `TARGET_LANG` (`France`) | **Set it together with `TARGET_LANG`.** The country of the readers, in its own language (`United States`, `México`, `Brasil`, `France`): the prompts say "for readers in …", and the translation follows its vocabulary, forms of address and spelling. It matters most for languages used in many countries: Spanish (`España` / `México` / `Argentina`), Portuguese (`Portugal` / `Brasil`), Chinese (`中国` / `台灣`), English (`United States` / `United Kingdom`), French, German, Arabic. Empty = a guess by the language (`en` → United States, `es` → España, `pt` → Portugal, `ru` → Россия, …; a language without one country → `<Language>-speaking countries`), and a run for es, pt, en, fr, de, zh or ar logs a warning |

---

## ⚡ Processing

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_LEN_CHUNK` | `8192` | Chunk size in source characters. The classic pipeline cuts only between blocks (paragraphs, poems between stanzas), so a single larger block stays whole |
| `LENGTH_CHECK_THRESHOLD` | `20` | Allowed deviation (%) from the expected translation length before a chunk is split and retranslated |
| `FAST_TRANS` | `false` | Skip stages 2-4 (both pipelines; `--fast-mode` turns it on too); the GENDER stage still runs |
| `MIXED_WORDS_WARN` | `10` | A final_edit output with more words in two alphabets (`dошло`) than this is logged as a WARNING; the report gives the largest count of one chunk. The words are only found and logged, never changed |
| `GENDER_CHECK` | `fix` | GENDER stage, both modes: a sentence where a dictionary character (gender `he`/`she`) is the subject and the verb or adjective has the other gender is found without an LLM (spaCy model of `TARGET_LANG` needed) and sent to the LLM for a fix (`fix`, the LLM is `GENDER_LLM`), only logged (`warn`), or not checked (`off`) |
| `PARALLEL_STAGES` | `1` | `2`: the next chunk's translation starts while the proofread LLM still works on this one (two LLM servers or a hosted API; ~1.4–1.5× faster). The next chunk then gets the synopsis of this chunk's draft. No effect with `FAST_TRANS` |
| `GENDER_LLM` | `auto` | LLM of the GENDER call: `auto` — proofread, with `FAST_TRANS` too, unless it is another model on the same local server as the translate LLM (one Ollama would swap the models every chunk), then translate; `translate` — always translate (`FAST_TRANS` with only the translate model loaded); `proofread` — always proofread |

**Details:** [RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md), [FAST_TRANS.md](FAST_TRANS.md)

---

## 📎 Dictionary and NER

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NER` | `true` | Build the dictionary from named entities on the first run (every format; the run then stops for review). Off: an empty template is created and terms are matched without spaCy. `--build-dict` runs NER regardless |
| `NERMODEL` | by `SOURCE_LANG` | spaCy model; empty = chosen from `SOURCE_LANG` and downloaded automatically (`en` → `en_core_web_lg`, `ko` → `ko_core_news_lg`, ...; full map in `src/config.py`); a language without its own spaCy pipeline (Turkish, Hungarian, Arabic, …) → multilingual `xx_ent_wiki_sm` |
| `DICT_FREQUENT_WORDS` | `false` | Also add frequent ordinary words (not named entities) to a new dictionary. Off: they fill the `.dic` with translations of common vocabulary. Per run for `--build-dict`/`--build-series-dict`: `--frequent-words` |
| `SPACY_AUTO_DOWNLOAD` | `true` | A missing spaCy model is downloaded on first use: the source model of the dictionary check and NER (`NERMODEL`), the small target model of the gender check (`ru_core_news_sm`, …). `false`: the check that needs it is skipped with a log line |
| `DICT_CHECK` | `true` | Check the dictionary against the source book before a translation (categories by NER, genders by pronouns; no LLM). See [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md#dictionary-check-before-a-translation) |
| `DICT_AUTOFIX` | `true` | Apply the sure findings of that check for the run (the `.dic` is not changed). `false` / `--no-autofix`: translate by the `.dic` as it is |
| `DICT_FORCE` | `true` | Without autofix: a dictionary contradicting the book is only reported. `false`: the run stops (exit code 2). CLI: `--force` (`true`) |
| `DICT_AUTO_SAVE` | `false` | Write the names and coined terms the synopsis stage finds while translating into the `.dic`. Off: they join the in-memory dictionary for the rest of the run (and its resume, via the checkpoint), but the file stays as you reviewed it. A candidate already covered by the dictionary is never added — neither another case or inflected form of an entry (`Jain nodes`, `Gabbleducks`) nor a phrase containing a known term (`Jain node`, `Jain-tech` when `Jain` is there). A hyphen, a space or no separator make different entries (`gabble-duck` is not `gabbleduck`). Works the same with `FAST_TRANS=on`: the synopsis stage is kept, so the dictionary grows in fast mode too (see [FAST_TRANS.md](FAST_TRANS.md)) |
| `DICTIONARY` | empty | Explicit path to the `.dic` file instead of `<book>_<lang>.dic` next to the book (`<lang>` — the ISO code of `TARGET_LANG`; built there when missing, a `<book>.dic` without the code is not used). CLI: `--dictionary <path>` (wins over `.env`). Both pipelines |

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
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — the stages of a chunk
- [RESUME.md](RESUME.md) — resume after a crash
- [DOCKER.md](DOCKER.md) — Docker
