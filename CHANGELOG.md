# Changelog

All notable changes to Sunny Narrator.

## Unreleased

### Internationalization (checked with English → Turkish)
- `COUNTRY` defaults from `TARGET_LANG` (`tr` → Türkiye); it was "Россия" for every target. Calibre pipeline functions take languages and country from the settings instead of `en`/`ru`/`Russia` defaults.
- The wrong-language retry works for every target: it compares the ordinary words of the output with the source (markup, numbers and capitalized names/terms not counted), and the retry replaces the first answer only when it is more translated. It only knew Russian, so an untranslated chunk passed as Turkish, French, German.
- The "translation may have failed" warning (EPUB writer, Calibre output) runs only for targets with their own script and counts all letters; it fired for every Latin-script target and for every translated Chinese/Japanese/Greek book.
- Turkish/Azerbaijani capitals in term substitution: `iksir` → `İksir`, not `Iksir`.
- The EPUB footnotes chapter is titled in the target language (`Notlar`, `Примечания`, …) instead of "Notes"; the EPUB language falls back to the target, not `en`.
- NER for a source language without a spaCy pipeline uses the multilingual `xx_ent_wiki_sm` (was the English model); its `PER` label is normalized; Turkish case suffixes after an apostrophe are cut (`Ankara'ya` → `Ankara`). An empty `NERMODEL=` now means "by `SOURCE_LANG`" as documented.
- TXT chapter headings are recognized in more languages (`Bölüm 3`, `3. Bölüm`, `Kapitel`, `Chapitre`, `Capítulo`, `第3章`, …).
- `scripts/convert_dic.py` is no longer tied to an English→Russian dictionary: `--source-lang` / `--hint-lang` (defaults `SOURCE_LANG` / `TARGET_LANG`).
- README in Turkish (`README_TR.md`).
- Tested languages listed in every README and in `docs/LANGUAGES.md`: real book translations (English → Russian, Korean → Russian); source languages verified on real spaCy models by `tests/test_languages_real_models.py` (English, Korean, Japanese, Chinese, Russian, German, French, Spanish, Portuguese, Italian; Turkish limited); target languages covered by automated tests (Russian, Turkish, German, Chinese).

### Prompts
- `prompts.json` rewritten: 21.7 KB → 12.6 KB, no repeated rule blocks, one directive per rule.
- Fixed: the reflection system prompt reached the model unformatted (literal `{target_lang} ({country})`): it used `{source_lang}`, which the caller never passed. `get_prompt` now logs every unformatted prompt, and `tests/test_prompts.py` checks each template against the variables of its call site.
- Fixed: EPUB/DOCX/PDF chunks (`user_text`) were translated without the glossary in the prompt.
- Fixed contradictions: the JSON translator was told to drop XML tags; the editor was told to "restore FB2 tags" it cannot see; improve was told to fix accuracy and apply the glossary without having either; the Markdown prompts spoke of FB2 tags; the retry prompt said "English" for any source language.
- The translator is told that glossary terms already substituted into the source are in base form and must be inflected; Markdown and image/HTML placeholders must be kept.
- Reflection writes self-contained fixes ("Replace «X» with «Y» — reason") or exactly `NO CHANGES`; improve always runs and then returns the text unchanged.
- Metadata: genre codes, dates, numbers and language codes are kept; glossary terms are translated in dictionary form.
- Unused keys removed (`*_hunyuan` of reflection/improve/editor/vocabulary, `vocabulary.system`, `metadata_translation.system`, JSON `user_xml`/`user_hunyuan`).

### Dictionary: growth without duplicates
- A name or coined term reported by the synopsis stage is added only when nothing of it is in the dictionary yet. Another case or inflected form of an entry is that entry (`Jain nodes` = `Jain node`, `Gabbleducks` = `gabbleduck`; a name by inflection only — `Jains` is `Jain`, `Marie` is not `Mary`; an ALL-CAPS acronym only by itself — `ECS` is not `EC`); a phrase containing a known term is skipped (`Jain node`, `Jain-tech`, `jain shriek`, `Jason Williams` when `Jain` / `Jason` are there). A hyphen, a space or no separator make different entries (`gabble-duck` / `gabbleduck`), so it no longer shadows the base entry with another translation. Of one batch the shorter candidate is taken first.
- The synopsis prompt gets the chunk's glossary (`<glossary>`) and is told not to report its terms, their forms or phrases built on them.
- New `DICT_AUTO_SAVE` (default `false`): found entries join the in-memory dictionary for the rest of the run and are kept in the checkpoint for a resume; the `.dic` file is written only when it is on. Previously every entry went into the file.
- Duplicate lines of one entry in a `.dic` (`Jain tech` / `jain tech`) are reported on load and the first one is kept (previously the last one silently won). When both `Jain tech` and `Jain-tech` are in the dictionary, both reach the prompt for a chunk with either spelling, and the substitution uses the literal one.
- Fixed: with CuPy installed (extra `[gpu]`) per-chunk term matching crashed (`Implicit conversion to a NumPy array is not allowed`) in both the GPU and the CPU variant, because the spaCy model keeps its vectors on the GPU after `prefer_gpu()`. A test now checks that both variants give the same result.
- NER no longer puts a leading article into an entity (`a Jain` → `Jain`, `l'Empire`, `der Kaiser`, `los Jain`, `一个吉恩人`) for English, French, German, Spanish, Portuguese, Italian and Chinese; a capitalized article (`The Warship`, `El Greco`) and name particles (`de la Vega`, `da Silva`) stay.

## v2.7

### Dictionary: priority and substitution
- A multi-word term takes priority over the shorter terms it contains (`Mad Hatter` over `Hatter`), then the longer one wins. A term that occurs only inside a longer one is no longer put into the prompt nor brought back by the cosine stage; the prompt lists the specific entries first.
- Substitution of terms into the source text before the first stage (`src/term_substitution.py`) follows the same priority and rules as matching. Tags, attributes, XML entities, markdown link targets, URLs and attribute blocks are never touched; a term does not span markup; whitespace and typographic apostrophes inside a term are tolerated; targets are XML-escaped in FB2. A lowercase term matches in any case (the target takes the capital), a name as written or in ALL CAPS (`Will` is not replaced in "will"); only an occurrence in the term's case shadows other terms.
- Fixed: substitution used to rewrite `<title>` and `l:href="#..."`, skipped `MAD HATTER`, `Queen’s Court`, `Mad⏎Hatter` and every CJK term, and missed a Latin term inside CJK text (`ABC社`, full-width `ＡＢＣ`).
- Coined words (`spidergun`) reported by the synopsis stage are appended to the `.dic` as `TERM`; only characters with a proper name are added as `PERSON`.
- One lexical pass per chunk with spaCy lemmas.
- `scripts/convert_dic.py`: convert a `.dic` to other target languages.

### CJK
- Korean entities go into the dictionary without the glued particle (`철수는` → `철수`, `서울에서` → `서울`), so a term matches every form of the word.
- New `cjk` extra (`pip install -e ".[cjk]"`): tokenizers for the Japanese (`sudachipy`, `sudachidict-core`) and Chinese (`spacy-pkuseg`) spaCy models; Korean needs nothing extra. Verified with `ko_core_news_lg`, `ja_core_news_lg`, `zh_core_web_lg`.

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
