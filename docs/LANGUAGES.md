# Tested languages

Any language the LLM can write works as a target, and any language works as a
source for the translation itself: prompts take the language from
`SOURCE_LANG`/`TARGET_LANG`. What differs per language is the code around the
LLM — the dictionary (NER, finding a term in its inflected forms, substitution)
and the target-specific checks. This page lists what has been verified and how.

**Levels**

- **Real translations** — whole books translated with real LLMs.
- **Real model** — automated tests on a real spaCy model
  (`tests/test_languages_real_models.py`; a case is skipped when its model is
  not installed).
- **Automated** — automated tests of the language-specific code with a faked
  LLM or faked tokens.

## Translation directions

| Direction | Level |
|---|---|
| English → Russian | Real translations (book series with a series dictionary) |
| Korean → Russian | Real translations |
| English → French, Spanish, Polish, Portuguese, Russian, Turkish, Chinese | Real translations: one book, seven targets, metrics [below](#real-translations-english--seven-languages) |
| English → Turkish | Real translation (above); also automated: all five stages of a chunk with a faked LLM (`tests/test_target_turkish.py`) |

## Real translations: English → seven languages

One book, `books/eternal-moment.pg.epub` (E. M. Forster, *The Eternal Moment and
Other Stories*, 230,923 source characters, 27 chunks of at most
`MAX_LEN_CHUNK=10000`), translated through the Calibre pipeline into seven
languages with the same dictionary of 38 terms (24 PERSON, 6 ORG, 5 TERM,
3 LOC; one `<book>_<lang>.dic` per language, the genders of 14-15 characters
are filled in from the synopsis). All five stages, JSON mode, local llama.cpp
servers: translate — Gemma 4
26B-A4B (UD-Q5_K_XL), proofread — Qwen 3.6 35B-A3B (Q4_K_M, MTP). One run per
language, one after another, on one machine.

| Target | Chunks translated¹ | Rechunk events | Tokens | Retry tokens | Time | Target size | Size vs source | Gender errors found / fixed | Words in two alphabets (final) |
|---|---|---|---|---|---|---|---|---|---|
| French | 28 | 1 | 740,683 | 0 (0.0%) | 47.3 min | 262,132 | +13.5% | 0 / 0 | 0 |
| Spanish | 28 | 1 | 682,946 | 0 (0.0%) | 42.4 min | 246,441 | +6.7% | 0 / 0 | 0 |
| Polish | 28 | 1 | 794,475 | 18,374 (2.3%) | 55.1 min | 233,254 | +1.0% | 1 / 1 | 0 |
| Portuguese | 30 | 3 | 676,648 | 46,137 (6.4%) | 50.6 min | 242,573 | +5.0% | 0 / 0 | 0 |
| Russian | 32 | 5 | 720,163 | 17,632 (2.4%) | 52.9 min | 231,173 | +0.1% | 0 / 0 | 0² |
| Turkish | 31 | 4 | 771,882 | 12,015 (1.5%) | 63.7 min | 228,267 | −1.2% | 0 / 0 | 0 |
| Chinese | 27 | 0 | 565,314 | 0 (0.0%) | 33.3 min | 82,185 | −64.4% | 0 / 0 | 0 |

¹ The 27 chunks plus the halves of the chunks that were split and translated
again. No chunk failed in any run (`Failed translations: 0`), so none stayed
untranslated.
² Three chunks had words in two alphabets in the INITIAL and IMPROVE stages
(17 words, `nкоторое`, `nОн`, …: a stray Latin `n` before the word); the
editor was told which words and the final texts have none.

**What caused the rechunk events** (a chunk is split in two and each half
translated again; 15 events in all, none left a hole):

- the REFLECTION answer was cut off at `max_tokens` (the model looped on the
  input): Polish 1, Portuguese 3, Russian 1, Turkish 1 — the retry tokens
  above;
- the length of the FINAL text was off the learned ratio by more than
  `LENGTH_CHECK_THRESHOLD`: French 1 (−15.8%), Russian 4 (+16% to +23%),
  Turkish 3 (the edited chunk came back at ×0.21 and ×0.25 of the source
  twice, then −19.8%), Spanish 1 (a 9,812-character chunk came back as 4,482,
  −57%).

**How the length ratio differs by language** (target characters / source
characters over the book): French 1.14, Spanish 1.07, Portuguese 1.05, Polish
1.01, Russian 1.00, Turkish 0.99, Chinese 0.36 — the ratio is learned per book, so the same
`LENGTH_CHECK_THRESHOLD` fits all of them.

**Dictionary:** every run logs the terms matched in each chunk
(`Lexical matches`, 27 chunks per run) and loads the 38-term dictionary at the
start; the dictionary check warns that 11 characters have no gender in the
`.dic`, 14-15 of them are then filled in from the synopsis by two agreeing
chunks.

**The files of these runs** are in the repository: the source book
`books/eternal-moment.pg.epub`, the seven dictionaries
`books/eternal-moment.pg_<lang>.dic` (so the first run of the demo book
translates at once), and in `books/samples/eternal-moment.pg/` the seven
translated EPUBs `The_eternal_moment__and_other_stories_<lang>.epub`, the
full log of every run `eternal-moment.pg_<lang>.log` (the source of the numbers
above) and the dictionary check `eternal-moment.pg.dictcheck.*`.

More directions (Spanish → English, Spanish → Russian) will be added here.

## Source languages (dictionary)

| Language | NER model checked | Term found in other forms | Entity cleanup | Level |
|---|---|---|---|---|
| English | `en_core_web_sm` (default `en_core_web_lg`) | yes (Snowball stem + spaCy lemma) | article `a`/`an`/`the` cut | Real translations, real model |
| Korean | `ko_core_news_sm`; `ko_core_news_lg` checked in v2.7 | yes (substring) | glued particle cut (`김철수는` → `김철수`) | Real translations, real model |
| Japanese | `ja_core_news_sm`; `ja_core_news_lg` checked in v2.7 (needs `pip install -e ".[cjk]"`) | yes (substring) | — | Real model |
| Chinese | `zh_core_web_sm`; `zh_core_web_lg` checked in v2.7 (needs `.[cjk]`) | yes (substring) | `一个`/`那位`… cut | Real model |
| Russian | `ru_core_news_sm` | yes (Snowball) | — | Real model |
| German | `de_core_news_sm` | yes (Snowball) | article cut (`die Jain` → `Jain`) | Real model |
| French | `fr_core_news_sm` | yes (Snowball) | article cut, `l'` too; `du`/`de` name particles kept | Real model |
| Spanish | `es_core_news_sm` | yes (Snowball) | article cut; `de la Vega` kept | Real model |
| Portuguese | `pt_core_news_sm` | yes (Snowball) | article cut; `da Silva` kept | Real model |
| Italian | `it_core_news_sm` | yes (Snowball) | article cut | Real model |
| Turkish | `xx_ent_wiki_sm` (no Turkish spaCy pipeline) | **exact form only** (no Turkish stemmer) | case suffix after an apostrophe cut (`Ayşe'nin` → `Ayşe`) | Real model, **limited** |
| Thai | — | yes (substring) | — | Automated (substitution only) |

Stop-word lists are also checked for Polish and Ukrainian.

**Turkish as a source is limited:** the multilingual model finds fewer names
and sometimes merges neighbours (`İstanbul'da Mehmet`), and a dictionary term
is found only in the form written in the `.dic`. Review a Turkish dictionary
by hand and add the inflected forms you need.

## Target languages

| Language | What is checked | Level |
|---|---|---|
| Russian | the whole pipeline; output file names, covers, metadata | Real translations, automated |
| French, Spanish, Polish, Portuguese | the whole Calibre pipeline on a real book; the gender check of the target (fr, es, pl, pt) | Real translations |
| Turkish | a real book through the whole pipeline; five stages with a faked LLM; capitals `iksir` → `İksir` in substitution; country `Türkiye` by default; untranslated-chunk detection for a Latin-script target; prompts | Real translations, automated |
| German | language marker in output file and cover names; country `Deutschland` by default | Automated |
| Chinese | a real book through the whole pipeline (output 0.36 of the source length); the EPUB "translation may have failed" check does not fire on translated Chinese text | Real translations, automated |

**Gender of the characters** (`src/gender_check.py`, `tests/test_gender_check.py`):
the GENDER stage checks the predicate of a dictionary character by the spaCy
model of the target language — past-tense verbs in Russian, Ukrainian, Polish
(and other Slavic languages with a model), participles with être/essere/ser
and predicative adjectives in French, Spanish, Portuguese, Italian (Catalan,
Romanian, Greek with a model). Checked on real models: ru, uk, pl, fr, es.
English, German, Dutch, Scandinavian languages and Chinese/Japanese/Korean
have no predicate gender — only the `<characters>` block of the prompts works
there; Turkish, Finnish, Hungarian and other languages without grammatical
gender of persons get no block.

**Words in two alphabets** (`src/script_guard.py`, `tests/test_script_guard.py`):
found and logged, not fixed — Latin letters inside a word of a Cyrillic
(ru, uk, be, bg, sr, mk, kk) or Greek target, Cyrillic letters inside a word
of a Latin-script target (Greek letters there are notation: `5 μm`, `Δx`).

Other targets get the generic behavior: the country defaults to
`<Language>-speaking countries` unless `COUNTRY` is set
(`src/config.py`, `_DEFAULT_COUNTRY`), the EPUB footnotes chapter falls back
to "Notes" when the language is not in `src/epub_writer.py`, `_NOTES_TITLE`.

## Running the language tests

```bash
pip install -e ".[cjk]"   # tokenizers of the Japanese and Chinese models
for m in en_core_web_sm de_core_news_sm fr_core_news_sm es_core_news_sm pt_core_news_sm \
         it_core_news_sm ru_core_news_sm ko_core_news_sm ja_core_news_sm zh_core_web_sm \
         pl_core_news_sm uk_core_news_sm xx_ent_wiki_sm; do
    python -m spacy download "$m"
done
pytest tests/test_languages_real_models.py tests/test_target_turkish.py tests/test_i18n.py \
       tests/test_gender_check.py tests/test_script_guard.py
```
