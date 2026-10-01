# Changelog

All notable changes to Sunny Narrator.

## v2.6

### Dictionary: one pipeline for all formats
- EPUB/DOCX/PDF (Calibre pipeline) now load, build, match and extend the dictionary through the same `VocabularyManager` as FB2/TXT. Glossary category and gender now reach the translation prompt for these formats too.
- A newly built dictionary stops the run for review in every format (previously DOCX/EPUB/PDF went on translating right away). Exit code 0, re-run to translate.
- Characters reported by the synopsis stage are written to the `.dic` and to the in-memory index during translation in every format, so the following chunks of the same run already use them.
- `--build-dict` uses the same builder and runs NER even with `NER=false`.

### Dictionary: term matching
- Terms are matched by word forms instead of an exact substring or `\b` regex: casefolded form, NLTK Snowball stem and spaCy lemma. `spidergun` finds `spiderguns`, `паукопушка` finds `паукопушками`, `wolf` finds `wolves`.
- Chinese, Japanese, Thai and Korean terms are matched as substrings (no spaces between words, particles glued to nouns); a Latin term inside CJK text is found too.
- A term no longer matches inside another word (`Ann` / `Annoying`), and a stem or lemma that is a stop word is ignored (`Ares` / `are`, `Wells` / `well`).
- spaCy runs on a chunk only when the lexical stage leaves terms unmatched; a spaCy model that cannot be loaded no longer aborts matching.

### Dictionary: building
- Frequent ordinary words are no longer added to a new dictionary by default — they filled the `.dic` with translations of common vocabulary. Enable with `DICT_FREQUENT_WORDS=true` or `--frequent-words`.
- Stop words for the source language (NLTK ∪ spaCy lists, incl. Japanese, Korean, Polish, Ukrainian) instead of English only; compared casefolded (German `daß`).
- Terms are translated by the proofread LLM for book and series dictionaries.
- The `.dic` is written only after every chunk of terms is translated: a failed or interrupted build no longer leaves a half-written dictionary that the next run would load as reviewed.
- Series dictionary (`--build-series-dict`): proper names keep their capitalization and all their words (`John Smith`, not `john`).
- The Calibre pipeline builds and matches the dictionary for the languages of the run.

### Other
- Calibre pipeline rechunking: a chunk that fails the length check is split at a paragraph break, a closing tag or a sentence end near its middle instead of mid-word.

## v2.5
- Reworked FB2 pipeline: chunks follow the section tree (nested sections, poems split between stanzas), LLM markup is repaired where it breaks, crash-safe resume.
- FB2 → EPUB via `--output-format epub` / `OUTPUT_FORMAT=epub` (nested TOC, footnotes, cover, images).
- Cover generation and the `sunny-narrator` command fixed.
- `env.sample` with Gemma 4 + Qwen 3.6 examples.
- Unused options removed (`CONCURRENT_LIMIT`, `COVER_PROMPT`, `S_PROMT_IMAGES`, `TEMP_IMAGES`, `SHORT`, `EXAMPLE`).
- Checkpoints from earlier versions are not resumed.

## v2.4
- `DICTIONARY` (`.env`) / `--dictionary` (CLI): explicit path to the `.dic` file for both pipelines.

## v2.3
- README overhaul: consolidated capabilities list, added CLI-only tool note, unified Docker registry links across all language versions, SEO improvements.

## v2.2
- Character gender detection written back to the dictionary.
- Per-book calibration of the translation length check.
- CJK adaptation (Korean, Japanese, Chinese) with direct translation from CJK into any language.

## v2.1
- Auto-detect pipeline by file extension (.docx/.epub/.pdf → Calibre; .fb2/.txt → classic); removed `--pipeline` flag.

## v2.0
- Migrated from pip requirements.txt to pyproject.toml; PyTorch CUDA 12.1 + cuPy.

## v1.4
- Added general workflow diagram and step-by-step instructions to README.

## v1.3
- Initial English README.

## v1.11
- Checkpoint/resume, empty response fallback, CPU Docker.

## v1.10
- remove_tags simplification, token stats fix.

## v1.9
- 5-stage pipeline, stage-specific temperatures.

## v1.0
- Initial release.
