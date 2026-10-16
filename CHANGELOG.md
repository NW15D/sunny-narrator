# Changelog

All notable changes to Sunny Narrator.

## v2.9.2

### Words in two alphabets: the last stages see the target language only
- The reflection fixes drop filter (`find` not in the translation, `replace` a word in two alphabets) is active only with `JSON_MODE=true` (default `false`); in text mode the prompts alone ask `improve` to skip unapplicable fixes.
- `improve` and `editor` JSON input no longer carries the glossary (English keys), `country`, `target_lang` or the source language; reflection writes its fixes in the target language only. JSON mode: `{"fixes": [{"find", "replace", "reason"}]}` (pairs that change nothing, or whose `find` is not in the translation, are dropped in code); text mode: `«X» → «Y» — reason`. The "Y differs from X" rule and the "names and acronyms stay" exception of the editor are gone.
- The translation prompts no longer say "exactly as given… keep them. Inflect" about terms already substituted into the source: such terms are ordinary target-language words to inflect.
- Fixed: in JSON mode the reflection reply was never parsed, so `improve` received the raw JSON lines as fixes.
- Reflection fixes whose `replace` is a word in two alphabets (`дредноута` -> `dредноута`) are dropped in code, like those whose `find` is not in the translation.
- `improve` and `editor` prompts state that the fixes, the translation and the output are in the target language (the instructions stay English). Length budgets of `improve`/`editor` raised by 10-30 characters for this.
- A Latin first letter of an otherwise all-Cyrillic word (`d`ойти, `T`акое) is a keyboard-layout slip and is now fixed deterministically (`script_guard.fix_mixed_first_letter`, applied after the mixed-words metric so the log stays honest): Cyrillic homoglyph substitution (d->д, t->т, c->с, …), case preserved, purely-Latin words untouched, noop for non-Cyrillic targets.
- `untranslated words` in reflection and editor no longer covers names and acronyms: legitimate Latin `FBI`, `NATO`, `iPhone` must not be "translated" back into Cyrillic. A fix `find` may quote a source-language word left in the translation; `improve` JSON input no longer claims every field is in the target language.
- Deletion fixes (empty `replace`) survive the parser; the `{"fixes": [...]}` wrapper is unwrapped inside the drop filter too. The Russian examples of the synopsis `dictionary_rules` became language-neutral placeholders.

### Dictionary
- New `DICT_FORCE` (default `true`): without autofix (`--no-autofix`, `DICT_AUTOFIX=false`) the run translates by the `.dic` as it is and only reports a dictionary contradicting the book; `DICT_FORCE=false` stops the run on a contradiction (exit code 2), as `--no-autofix` alone did before. `--force` stays, the same as `DICT_FORCE=true`; without `--no-autofix` it has no effect and says so. `DICT_AUTOFIX` is still on by default.
- With `DICT_FORCE=false` filling an empty category from the book no longer stops the run (filling an empty gender did not): only a category or a gender the book contradicts does.
- `app.py dict convert` returns its exit code like the other commands instead of calling `sys.exit` inside.

## v2.9.1

### Gender of the characters (small models)
- New GENDER stage after the last text stage, in both modes — `FAST_TRANS` too. Without an LLM it finds the sentences where a dictionary character with gender `he`/`she` is the subject and the verb or adjective has the other gender (`Вашти сказал`, `Ellen était fatigué`), by the spaCy model of the target language (`src/gender_check.py`); the found sentences go to the LLM in one short call (`gender_fix` prompt: the sentences, the wrong words, the character's gender), and a fixed sentence replaces the original only when the check passes, the markup is the same and only a few words changed. `GENDER_CHECK=fix|warn|off` (default `fix`), `TEMP_GENDER` (default `0.05`). Checked: Slavic languages (verb gender: ru, uk, pl, …), French, Spanish, Portuguese, Italian, Catalan, Romanian, Greek (participles with être/essere/ser, predicative adjectives); languages without the model or without predicate gender are not checked. Pronouns a few sentences away are not checked: a pronoun may refer to anything.
- The gender left the glossary lines (`Vashti = Вашти, PERSON, she`) for a `<characters>` block in every stage (translation, reflection, improve, editor; JSON mode too): `Вашти — она (сказала)`, written the way the target language shows it. The editor saw no gender at all before and was told to fix gender agreement. Reflection checks the gender first.
- The synopsis infers a gender from the pronouns of the source, not from the translation, and a gender it reports becomes the character's only when two chunks agree; a disagreement is logged and leaves the gender empty, a report against the `.dic` is logged. A small model that misgendered one draft no longer fixes that gender for the rest of the run.
- A new dictionary gets its genders from the book, not from the model (see "A new dictionary takes its categories and genders from the book" below); on load, characters without gender are listed in the log, and the spellings of the gender field (`female`, `она`, `ж`, …) become `he`/`she`/`it`/`they`; an unknown value is ignored with a warning, so the synopsis can still fill the gender in. The synopsis, `--build-dict` and `app.py dict clean` use the same list.
- The GENDER stage never costs a chunk its translation: a failure in it (a truncated reply, an API error) keeps the translation as it is. A sentence soft-wrapped over several lines (pandoc Markdown) is sent as one line, keeping its no-break spaces; one across list items, quote or verse lines is never merged. The gender votes of the synopsis are kept in the checkpoint as one record.
- New `GENDER_LLM=auto|translate|proofread` (default `auto`: proofread; with `FAST_TRANS` too, unless it is another model on the same local server — one Ollama for both would swap the models every chunk; a hosted API serving both swaps nothing). `translate` for `FAST_TRANS` with only the translate model loaded.

- Checked on a real run (The Warship, ru): the gender check had 7 false findings of 24, and the GENDER stage "fixed" some of them by rewriting another character's verbs. Now a name counts only in its dictionary (nominative) form ("Ангела", "Клиентки" are other cases the parser misread); a gerund or infinitive has no gender; Slavic forms are checked by their ending too ("повреждён" tagged feminine); a joined verb with another subject before it belongs to that subject ("Король хотел, чтобы Спраг установила…, выступила…"). A fix is taken only when it changes the endings of all the flagged words and nothing else. On that run: 17 of the 24 findings stay, the 7 false ones are gone.
- The gender check parses the text block by block (paragraphs, headings, verses): a chapter heading was read as the subject of the next paragraph ("### Диана" + "Кингхаммер пришел" -> "Диана пришел"). The Warship, ru, before / after the changes of this release: gender errors found by `app.py audit` 55 -> 7, all 7 false findings the current check no longer makes; words in two alphabets 28 -> 17.
- The dictionary review on a science-fiction dictionary turned characters into ORG (NER tags invented names so: Trike, Cog, the Client) and a name into TERM because of the ordinary word ("Stone" / "stone"). Now a PERSON the book calls he/she stays a person, a lowercase word is not a mention of a capitalized name, and only an entry written lowercase in the `.dic` can become TERM by its spelling.

### Words in two alphabets
- New `src/script_guard.py` finds the words the model wrote in two alphabets (`dошло`, `Gород`, `taкого`): Latin letters in a word of a Cyrillic or Greek target, Cyrillic ones in a Latin-script target (Greek letters there are notation — `5 μm`, `Δx`). They are logged per chunk and counted in the metrics report, not fixed: they appeared after the prompt rewrite of 2026-10-03, so the cause is looked for in the prompts (`app.py eval --prompts / --no-glossary / --no-substitution`). A dictionary candidate of the synopsis written in two alphabets is not added; a GENDER fix that adds such a word is rejected.
- The editor prompt no longer tells the model to keep "Latin-script terms as they are".

### Prompts: one pipeline
- The translation stage knows the readers' country (`for readers in {country}`), as reflection and the editor did: with `FAST_TRANS` the localization (pt-BR / pt-PT, es-ES / es-MX) was not asked for at all.
- The JSON variants carry the rules of the text ones: the translator knows about the terms already replaced in the source and the country, "omit nothing, add nothing"; improve adjusts nearby words only for grammar and skips a suggestion that would break markup; the editor keeps names and acronyms and does not shorten or add.
- Duplicates removed: the two glossary rules of the translation stage are one; `initial_translation.user_hunyuan` no longer repeats its system prompt; `synopsis.user_hunyuan` (the same text as `synopsis.user`) is gone. In the glossary prompt "if unsure, keep the source term" applies to coined words only, not to names.
- Fix: with `MODEL_TRANSLATE=Hunyuan` the metadata were sent with an empty prompt (`metadata_translation.user_hunyuan` does not exist).
- With `FAST_TRANS` the GENDER stage goes to the proofread LLM unless that is another model on the translate LLM's local server (it follows edit instructions better than a translation model), otherwise to the translate LLM.
- `tests/test_prompts.py`: every prompt key the code asks for exists; the text and JSON variants of a stage carry the same rules; every stage that writes text has the gender rule; each prompt has a length budget.

### The dictionary is checked before every translation
- Both pipelines check the dictionary against the source book right after loading it (`src/dict_review.py`, no LLM): categories by the NER labels of the entries' mentions, genders by the pronouns of the sentences naming one character. The sure findings (more than three pieces of evidence, 85 % for one side) are applied for the run — the `.dic` is not changed, `<dic>.reviewed.dic` gets them; the report is `<book>.dictcheck.txt`, the result is cached in `<book>.dictcheck.json`. `--no-autofix` (`DICT_AUTOFIX=false`): a dictionary contradicting the book stops the run (exit code 2), `--force` translates as is. `DICT_CHECK=false` turns the check off. A dictionary just built gets the findings into its own file before the stop for review.
- Multilingual: the NER labels of OntoNotes, WikiNER, Polish and Korean spaCy models, pronoun gender by `Person=3`/`Person=Third` morphology, Chinese/Japanese/Korean pronouns by their form, a sentencizer for a model without a parser.
- The synopsis reports a gender (`<genders>`) only for characters the dictionary has no gender for; a gender it fills in is logged and listed in the run report. The run report also lists the characters the translation keeps disagreeing with the dictionary on (the GENDER stage findings): a wrong gender in the `.dic` shows there.

### A new dictionary takes its categories and genders from the book
- NER: the characters of books in German, French, Spanish, Italian, Portuguese, Russian and Ukrainian (and with `xx_ent_wiki_sm`) never reached the dictionary — their models label people `PER`, which was not on the list; the Polish `persName/placeName/orgName` labels were not either. One table of labels → categories (`ner.CATEGORY_OF_LABEL`) now serves building and checking a dictionary; peoples and species (`NORP`, `MISC`) become TERM.
- One entry per entity: the forms are grouped by lemma (the nominative "Москва", not "Москву"), the category is the majority of the mentions, not the label of whichever variant survived.
- The LLM only translates the glossary: its guessed categories and genders (by the name alone) are no longer used. The categories and genders are decided by the book and written into the new `.dic`: an entry the book keeps calling he/she is a PERSON with that gender (NER tags invented names ORG), a lowercase word is a TERM, a form of address ("Miss", "Mr.", "Signora", "мисс", "Frau") decides a gender before the pronouns, and a gender the evidence disagrees on stays empty and is reported. On the demo book: 10 of 24 characters get a gender, all right (8 right and one wrong before, "Harbottle" he); the rest are listed for the review.

- A dictionary shared by a series is never changed by a translation run: the check before each book fixes it in memory for that run, against that book; the findings go to `<dic>.<book>.reviewed.dic` (one per book — they overwrote each other in one `<dic>.reviewed.dic`) and `<book>.dictcheck.txt`.

### Commands instead of scripts
- The Python tools of `scripts/` are commands of the application: `app.py dict clean|review|convert`, `app.py audit`, `app.py eval`, `app.py clean-calibre` (`python app.py <command> -h`; `docs/DICTIONARY_FORMAT.md`). `scripts/cleanup_calibre_markup.py` was a copy of the Calibre pipeline's cleanup and is gone; `scripts/` keeps the shell tools only.

### Measurement
- New `app.py audit`: words in two alphabets, gender errors and characters without gender in a finished book, with `--compare` against an earlier run.
- New `app.py eval`: the passages of a book with the most gendered characters, translated by the real pipeline with the `.env` models, measured the same way and compared with an earlier run.
- New `app.py dict review`: categories and genders of a `.dic` checked against the source book without an LLM — the category by the NER labels of the entry's mentions (PERSON → LOC/ORG, TERM → PERSON; an entry written lowercase in the book → TERM), the gender of a person by the pronouns of the sentences naming only them. Sure findings go to `<name>.reviewed.dic` (the source `.dic` is not changed, its lines and comments are kept), the rest with all the evidence to the report; a gender already in the `.dic` that the book contradicts is only reported. On the demo books: `Vorta` (a village) is no longer PERSON, every gender set is right, `Shelley … she` is reported (the book says he), two-person scenes (Kuno he ×17 / she ×14) stay unsure.
- `app.py eval` A/B switches for this run only: `--prompts FILE` (other prompts over the current ones, e.g. the version before a rewrite), `--no-glossary`, `--no-substitution`; the variant is saved in the result and shown by `--compare`.
- Metrics report: words in two alphabets, gender errors found/fixed.

### Defaults
- `FAST_TRANS` defaults to `false` in the code, as in `env.sample` (it was `on`).

## v2.9

### Translation
- New `PARALLEL_STAGES` (default `1`): `2` overlaps the translate stages of the next chunk with the proofread stages of the current one, for the translate and proofread LLMs on separate GPUs (each GPU serves one request at a time, so more than 2 gains nothing). On the logs of real books the translate side (S1 + synopsis) takes 34–38% of the time, so the expected gain is about 1.4–1.5× (ceiling 1.5–1.6×). The price: in this mode the synopsis and the dictionary candidates come from the first translation (S1), not from the final one — the next chunk needs them before the proofreading of the previous one is over. Both pipelines (classic and Calibre) use it; the order of the output, checkpoints (they hold the state as of their own chunk), retries, rechunking and the error handling are unchanged. Not used with `FAST_TRANS` (no proofread stages). The mechanism is `src/stage_pipeline.py`.
- A chunk that fails in the pipeline (`finish_reason='length'` after the model loops, a malformed response, an API error) is translated as two halves and glued back, in both pipelines; retrying the same input usually loops again. A half that fails re-raises the original error, so the whole-chunk retries still run.

### FAST_TRANS and resume: one behaviour for both pipelines
- DOCX/EPUB/PDF: `FAST_TRANS` from `.env` now applies to the Calibre pipeline too (it took only `--fast-mode`). Both pipelines read fast mode from one setting; with `FAST_TRANS` unset (default `on`) these books are now translated in fast mode as well — set `FAST_TRANS=false` for the full 5 stages.
- `--fresh` works for FB2/TXT too: the checkpoint is removed and the book is translated from scratch. In the Calibre pipeline `--fresh` now also drops the chunk checkpoint (it ignored only the finished translation dump), so neither old chunks nor the dictionary entries found by the old run come back.
- In `FAST_TRANS` mode the dictionary grows by the same rules (the synopsis stage is kept), but its candidates come from the unproofread first translation, and a translation under 200 characters gets no synopsis. New two-pass recipe (`docs/FAST_TRANS.md`, every README): a fast pass with `DICT_AUTO_SAVE=true`, review of the `.dic`, then `FAST_TRANS=false --fresh`.

### Output names
- Classic pipeline (FB2/TXT): the language marker in output names is taken from `LANG_CODE_MAP`, as in the Calibre pipeline — `TARGET_LANG=russian` now writes `Book_ru_1530-2909.fb2` and `Book_ru_cover.png` (was `Book_russian_…`). A language missing from the map keeps its name, lowercased (`serbian`). A checkpoint left under the old name is still resumed. Both pipelines take the marker from one place (`Config.lang_marker`).

### Docker and CI
- Docker: both images (GPU and CPU) include Calibre (`ebook-convert`) and pandoc (3.12, pinned), so EPUB/DOCX/PDF books are translated in the container too. The GPU image is based on `nvidia/cuda:12.6.3-runtime-ubuntu24.04` (Python 3.12, `torch 2.14.1+cu126`, the project in `/opt/venv`). The CPU image is based on Python 3.11: it was on 3.10, below the project's `requires-python`, and did not build.
- CI: both images are built and the test suite runs inside each of them (`scripts/docker-ci-test.sh`; the Calibre test must not be skipped there) — in GitLab (`docker-images` job, a privileged runner tagged `docker`) and in GitHub Actions, which then pushes them to GHCR: GPU as `main`, `2.9`, …, CPU as `main-cpu`, `2.9-cpu`, …. Pull requests build and test without pushing. `books/` is mounted read-write, since the translation and its checkpoint are written next to the book. `scripts/test-docker.sh` uses the existing `docker-compose.yml` (it pointed to a missing `docker-compose.gpu.yml`), its checks override the `app.py` entrypoint, and it checks Calibre and pandoc.

### Demo books
- `demo.sh` translates the demo books one after another into ru, es, fr, pl, pt, tr, zh, each with its own dictionary (`<book>_<lang>.dic`); the log of every run goes to `logs/<book>_<lang>.log`.
- Translated samples of *The Eternal Moment* in `books/` (ru, es, fr, pl, pt).
- The sample book of the tests is `books/eternal-moment.pg.epub`; the default `FILE` is `books/ExampleBook.fb2`, as in `env.sample` (`books/Cargo.fb2` was removed).

### Tools
- New `scripts/clean_dic.py`: cleans a `.dic` into a new file with a report — merges duplicates by the loader's rule (`lexicon.word_key`), normalizes gender synonyms (an unknown value is kept and reported), drops ordinary words by the vectors of the NER model (`--model`, `--keep`) and cut variants; every field is CSV-quoted as needed, so the result loads without losses.

## v2.8

### Dictionary: growth without duplicates
- A name or coined term reported by the synopsis stage is added only when nothing of it is in the dictionary yet, so compounds no longer shadow the base entry with another translation. Another case or inflected form of an entry is that entry (`Jain nodes` = `Jain node`, `Gabbleducks` = `gabbleduck`; a name by inflection only — `Jains` is `Jain`, `Marie` is not `Mary`; an ALL-CAPS acronym only by itself — `ECS` is not `EC`); a phrase containing a known term is skipped (`Jain node`, `Jain-tech`, `jain shriek`, `Jason Williams` when `Jain` / `Jason` are there). A hyphen, a space or no separator make different entries (`gabble-duck` / `gabbleduck`). Of one batch the shorter candidate is taken first. The file and the in-memory dictionary share one set of rules.
- The synopsis prompt gets the chunk's glossary (`<glossary>`) and is told not to report its terms, their forms or phrases built on them.
- New `DICT_AUTO_SAVE` (default `false`): found entries join the in-memory dictionary for the rest of the run and are kept in the checkpoint for a resume; the `.dic` file is written only when it is on. Previously every entry went into the file.
- Duplicate lines of one entry in a `.dic` (`Jain tech` / `jain tech`) are reported on load and the first one is kept (previously the last one silently won). When both `Jain tech` and `Jain-tech` are in the dictionary, both reach the prompt for a chunk with either spelling, and the substitution uses the literal one.
- NER no longer puts a leading article into an entity (`a Jain` → `Jain`, `l'Empire`, `der Kaiser`, `los Jain`, `一个吉恩人`) for English, French, German, Spanish, Portuguese, Italian and Chinese; a capitalized article (`The Warship`, `El Greco`) and name particles (`de la Vega`, `da Silva`) stay.

### Prompts
- `prompts.json` rewritten: 21.7 KB → 12.6 KB, no repeated rule blocks, one directive per rule.
- Fixed: the reflection system prompt reached the model unformatted (literal `{target_lang} ({country})`): it used `{source_lang}`, which the caller never passed. `get_prompt` now logs every unformatted prompt, and `tests/test_prompts.py` checks each template against the variables of its call site.
- Fixed: EPUB/DOCX/PDF chunks (`user_text`) were translated without the glossary in the prompt.
- Fixed contradictions: the JSON translator was told to drop XML tags; the editor was told to "restore FB2 tags" it cannot see; improve was told to fix accuracy and apply the glossary without having either; the Markdown prompts spoke of FB2 tags; the retry prompt said "English" for any source language.
- The translator is told that glossary terms already substituted into the source are in base form and must be inflected; Markdown and image/HTML placeholders must be kept.
- Reflection writes self-contained fixes ("Replace «X» with «Y» — reason") or exactly `NO CHANGES`; improve always runs and then returns the text unchanged.
- Metadata: genre codes, dates, numbers and language codes are kept; glossary terms are translated in dictionary form.
- Unused keys removed (`*_hunyuan` of reflection/improve/editor/vocabulary, `vocabulary.system`, `metadata_translation.system`, JSON `user_xml`/`user_hunyuan`).

### Internationalization (checked with English → Turkish)
- `COUNTRY` defaults from `TARGET_LANG` (`tr` → Türkiye); it was "Россия" for every target. Calibre pipeline functions take languages and country from the settings instead of `en`/`ru`/`Russia` defaults.
- The wrong-language retry works for every target: it compares the ordinary words of the output with the source (markup, numbers and capitalized names/terms not counted), and the retry replaces the first answer only when it is more translated. It only knew Russian, so an untranslated chunk passed as Turkish, French, German.
- The "translation may have failed" warning (EPUB writer, Calibre output) runs only for targets with their own script and counts all letters; it fired for every Latin-script target and for every translated Chinese/Japanese/Greek book.
- Turkish/Azerbaijani capitals in term substitution: `iksir` → `İksir`, not `Iksir`.
- The EPUB footnotes chapter is titled in the target language (`Notlar`, `Примечания`, …) instead of "Notes"; the EPUB language falls back to the target, not `en`.
- NER for a source language without a spaCy pipeline uses the multilingual `xx_ent_wiki_sm` (was the English model); its `PER` label is normalized; a Turkish case suffix after an apostrophe is cut (`Ankara'ya` → `Ankara`), a foreign name stays whole (`O'Brien`). An empty `NERMODEL=` now means "by `SOURCE_LANG`" as documented.
- TXT chapter headings are recognized in more languages (`Bölüm 3`, `3. Bölüm`, `Kapitel`, `Chapitre`, `Capítulo`, `第3章`, …).
- `scripts/convert_dic.py` is no longer tied to an English→Russian dictionary: `--source-lang` / `--hint-lang` (defaults `SOURCE_LANG` / `TARGET_LANG`).

### Languages, documentation, tests
- Tested languages listed in every README and in `docs/LANGUAGES.md`: real book translations (English → Russian, Korean → Russian); source languages verified on real spaCy models by `tests/test_languages_real_models.py` (English, Korean, Japanese, Chinese, Russian, German, French, Spanish, Portuguese, Italian; Turkish limited); target languages covered by automated tests (Russian, Turkish, German, Chinese).
- README in Turkish (`README_TR.md`); the dictionary sections of every README describe `DICT_AUTO_SAVE` and the duplicate rules.
- `tests/test_prompts.py` checks every prompt template against the variables of its call site; `tests/test_languages_real_models.py` runs the source languages on real spaCy models.

### GPU
- Fixed: with CuPy installed (extra `[gpu]`) per-chunk term matching crashed (`Implicit conversion to a NumPy array is not allowed`) in both the GPU and the CPU variant, because the spaCy model keeps its vectors on the GPU after `prefer_gpu()`. A test now checks that both variants give the same result.

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
