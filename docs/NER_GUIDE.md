# NER Guide — Names and Terms of a Book

spaCy does two jobs in Sunny Narrator, without an LLM:

1. **Building a dictionary** — the named entities of a book (people, places,
   organizations, coined terms) become the entries of a new `.dic`; the
   proofread LLM only translates them. Categories and genders come from the
   book itself (see [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md)).
2. **Matching per chunk** — before a chunk is translated, the dictionary
   entries that occur in it are found (in any inflected form), put into the
   prompt and substituted into the source.

Both pipelines (FB2/TXT and EPUB/DOCX/PDF) use the same code:
`VocabularyManager` (`src/vocabulary_manager.py`), `src/lexicon.py`,
`src/ner.py`. Languages verified on real spaCy models and their limits:
[LANGUAGES.md](LANGUAGES.md).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NER` | `true` | Build a missing dictionary with NER; `false` — an empty template (`--build-dict` runs NER anyway) |
| `NERMODEL` | by `SOURCE_LANG` | The spaCy model of the source language: `en_core_web_lg`, `ru_core_news_lg`, `ko_core_news_lg`, `ja_core_news_lg`, `zh_core_web_lg`, … (`Config.lang_model_map`); a language without its own pipeline gets `xx_ent_wiki_sm` |
| `SPACY_AUTO_DOWNLOAD` | `true` | A missing model is downloaded on first use |
| `DICTIONARY` | — | An explicit `.dic` instead of `<book>_<lang>.dic` next to the book (see [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md)) |
| `DICT_FREQUENT_WORDS` | `false` | Also put frequent ordinary words into a new dictionary |

**Model size matters for one thing — word vectors.** `*_lg` and `*_md`
models have them, `*_sm` and `*_trf` do not. Without vectors the cosine stage
of the matching finds nothing and `dict clean` / `dict extend` cannot tell an
ordinary word from a coined one; NER and the lexical stage work with any
model.

### GPU

Optional: `pip install -e ".[gpu]"` (CuPy for CUDA 12). spaCy then runs NER
and the word vectors on the GPU; the per-chunk matcher takes its GPU variant
when CuPy sees a device (`ner.gpu_available()`). No torch is needed. With an
`*_sm`/`*_lg` model the GPU stays almost idle — only the small networks run
there — and the gain is small; CUDA numbers the GPUs fastest first, so check
the right one (see [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md#gpu-cuda-and-cpu-nuances-of-dictionary-work)).

## Lexical matching (stage 1)

The same matcher runs for every input format — FB2/TXT (classic pipeline)
and EPUB/DOCX/PDF (Calibre pipeline) both go through
`VocabularyManager.get_vocab_for_chunk()`. Stage 1 is `lexicon.find_terms()` / `resolve_terms()`:

- Words are split by Unicode category (letters/marks/digits), not by regex,
  so it works for any script. A multi-word term must match consecutive words.
- **Priority** (`lexicon.term_rank`): a term of more words beats the shorter
  terms it contains (`Mad Hatter` over `Hatter`), then the longer one, then
  the leftmost. Words are counted as the matcher splits them, so
  `Jean-Luc-Marie` is three words. A term whose every occurrence is covered
  this way is dropped from the chunk (`lexicon.resolve_terms` also reports it
  as *shadowed*, so the cosine stage does not bring it back), and the prompt
  lists entries in priority order.
- **Case:** only an occurrence in the term's capitalisation (inflection
  allowed: `Mad Hatters`) or in ALL CAPS shadows other terms. In "the mad
  Hatter" both `Mad Hatter` and `Hatter` stay in the prompt and `Hatter` is
  substituted. A lowercase term (`spidergun`) fits any case.
- **Markup is not text** (`lexicon.non_text_spans`): FB2/HTML tags, markdown
  link and image targets, reference definitions, attribute blocks
  (`{#id .class}`) and URLs never match, and no term spans across them, so
  `Mad</p><p>Hatter` (two paragraphs) and `Mad <emphasis>Hatter</emphasis>`
  are not the phrase. A tag must have well-formed attributes to count
  (`fb2_structure.markup_tags`): `a<b and c>d` and pandoc-escaped
  `\<Skill acquired: Spidergun\>` are text. XML entities (`&amp;`, `&#38;`) are not
  words (a term `amp` never matches inside `&amp;`), and a markdown
  reference definition needs a URL-like target: `[Level]: 5 Hatter` is text.
- Two words match when they share a key: casefolded form, NLTK Snowball
  stem (en, ru, de, fr, es, it, pt, nl, sv, da, nb, fi, ro, hu, ar) or the
  spaCy lemma of the chunk word. `spidergun` finds `spiderguns`,
  `паукопушка` finds `паукопушками`, `wolf` finds `wolves` (lemma).
- Terms in scripts without spaces between words (Chinese, Japanese, Thai,
  …) and Korean (particles glued to nouns: `철수는`) are matched as
  substrings.
- A term never matches inside an unrelated word (`Ann` ≠ `Annoying`).
- Stems and lemmas that are stop words are ignored, so a name ending in -s
  does not collapse onto a common word (`Ares` ≠ `are`, `Wells` ≠ `well`).
  Rare stem collisions remain possible (`universe`/`university`); they only
  add an extra glossary line to the prompt.

spaCy runs once on the chunk; its lemmas feed stage 1 (a single
`find_terms` pass over surface forms, stems and lemmas), and its word vectors
feed stage 2 for the terms still unmatched. With `NER=false`, or if the spaCy
model cannot be loaded, only the spaCy-free search runs (surface forms +
stems).

Stop words used when building a dictionary come from `lexicon.get_stop_words()`:
NLTK list (≈30 languages) ∪ spaCy list (every spaCy language, incl. ja, ko,
pl, uk, hr, lt, mk) for the source language, plus fiction-specific extras for
English. They are casefolded, so look words up with `lexicon.is_stop_word()`
(German `daß` → `dass`).

## Cosine matching (stage 2)

The terms stage 1 did not find are compared by word vectors: the mean vector of
the term's words against the chunk's words, cosine similarity above 0.8. It
catches a term written differently (a synonym the vectors put close), costs
almost nothing, and is skipped with a model without vectors. The GPU and CPU
variants give the same result (`tests/test_ner_gpu_cpu_parity.py`).

## Building a dictionary

`VocabularyManager.build_dictionary()` builds every dictionary — a translation
run of any format and `--build-dict`; `--build-series-dict` uses
`ner.create_series_vocab()`. Both:

- extract named entities with NER (frequent ordinary words only with
  `DICT_FREQUENT_WORDS=true` / `--frequent-words`);
- translate the terms with the **proofread** LLM;
- write the `.dic` atomically once every chunk is translated, so a failed or
  interrupted build leaves no half-written dictionary for the next run.

The book's own languages are used (the Calibre pipeline passes the languages
of `run_pipeline()`; default `SOURCE_LANG`/`TARGET_LANG`/`COUNTRY`).
`--build-dict` runs NER even with `NER=false`. The series dictionary groups
entity forms by the lemmas of all their words and writes the form that is its
own lemma (else the most frequent one) with its original capitalization:
`John Smith`, `Иван` — not `john`.

## Substitution before the first stage

`src/term_substitution.py` (`replace_vocab_in_text`) replaces the terms of
the chunk in the source text before Stage 1, so the model cannot skip them.
Only names (`PERSON`, `LOC`, `ORG`) and multi-word terms are put in
(`substitution_terms`); an ordinary one-word `TERM` stays in the glossary of
the prompt.
It follows the matching rules above: the same priority, the same notion of
markup (tags, link targets, URLs and attribute blocks are never touched, no
term across them); occurrences never overlap. Words may be separated by any
whitespace, apostrophes may be typographic, CJK terms need no word
boundaries; a Latin term inside CJK text (`ABC社の製品`, also full-width
`ＡＢＣ`) is a word of its own. A lowercase term matches in any case (the target takes over the
capital), a term with capitals matches as written or in ALL CAPS (`Will` is
not replaced in "will"). In the classic pipeline (`style='xml'`) the chunk is
serialized FB2: terms are looked up and targets inserted XML-escaped
(`AT&amp;T`, `Б&amp;К`). Inflected forms (`Hatters`) are not substituted —
the model gets them through the glossary lines of the prompt. Stages 2–4
see the original.

## CJK sources

- **Models** (`SOURCE_LANG` picks them, `NERMODEL` overrides): `ko_core_news_lg`,
  `ja_core_news_lg`, `zh_core_web_lg`. Japanese and Chinese need their
  tokenizers (`pip install -e ".[cjk]"`: sudachipy, sudachidict-core,
  spacy-pkuseg); Korean uses spaCy's own tokenizer. Checked with all three
  models: lexical match, lemmas, cosine stage, entity extraction and
  substitution.
- **Stop words:** NLTK (Chinese) ∪ spaCy lists of the language, so Chinese
  has ~1800 entries, Japanese ~160, Korean ~65, Thai 7. Terms in unspaced
  scripts are matched as substrings and are not filtered by stop words
  (the dictionary is what the user reviewed); stop words only filter NER
  output and candidates.
- **Korean particles:** the Korean model tags `철수는` as `ncn+jxt` with the
  lemma `철수+는`. `ner.entity_text` cuts the trailing particle (tag `j*`)
  of the entity's last word, so the `.dic` gets `철수`, `서울`, `영희` and
  not one inflected form. The lemmatizer stays enabled for Korean only.
  A short name still matches inside a longer one (`철수` in `김철수`): that
  is the price of substring matching for glued particles.
- **Priority** works the same: `魔王城` beats `魔王` where they overlap, and a
  line break inside a term is not skipped (`魔王⏎城` is not `魔王城`).
- **Known limits:** NER quality depends on the model (`韩梅梅` may come out as
  `韩梅`); `ner.known_words` filters coined one-word terms by word vectors,
  so a word the model knows (`거미총` in ko) is treated as an ordinary word.

## Troubleshooting

| Symptom | Check |
|---|---|
| A term of the dictionary never reaches the prompt | Is it shadowed by a longer term that contains it (`DEBUG=1` prints the lexical matches of every chunk)? Is its case right — `Will` does not match "will"? |
| Ordinary words in a new dictionary | `dict clean` drops them (needs a model with vectors); `DICT_FREQUENT_WORDS` must be `false` |
| `spaCy model … is not available` | Offline or `SPACY_AUTO_DOWNLOAD=false`: `python -m spacy download <model>` |
| Japanese/Chinese model fails to load | `pip install -e ".[cjk]"` |
