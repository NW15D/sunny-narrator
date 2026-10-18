# Working with Dictionaries (.dic files)

**Version:** 1.1 (CSV with commas)  
**Last Updated:** 2026-10-16  
**Issue:** Format mismatch fixed (was incorrectly documented as JSON). Moved here from the README: all dictionary commands and rules, the series workflow, and the spaCy / CUDA / CJK nuances of dictionary work.

---

## Overview

The dictionary file (`*.dic`) ensures terminology consistency throughout translation. It contains:
- Character name translations
- Geographic locations
- Domain-specific terminology
- Gender information for correct pronoun usage

### Commands at a glance

| Task | Command / step |
|---|---|
| New book, no dictionary | `python app.py` (or `python app.py --build-dict books/MyBook.epub`) → `books/MyBook.dic` + `books/MyBook.dictcheck.txt` → fill in the empty genders you know → run again |
| Translate with a dictionary | `python app.py` — the check runs first; read `<book>.dictcheck.txt`, take `<dic>.reviewed.dic` if you agree |
| Strict mode | `python app.py --no-autofix` — by the `.dic` as it is; `DICT_FORCE=false` — stops on a contradiction (exit code 2) |
| Series of books | `python app.py --build-series-dict books/series/ --series-dict-output series.dic`, then each book with `--dictionary series.dic`; a run never changes `series.dic`, each book gets `series.<book>.reviewed.dic` |
| Clean a dictionary | `python app.py dict clean books/MyBook.dic` → `MyBook.clean.dic` + report (duplicates, gender spellings, ordinary words) |
| Carry a dictionary over to a new volume / book of the universe | `python app.py dict extend series.dic --book vol3.epub [--merge other.dic]` → `series.extended/series.dic` + `series.extend.report.txt` (see *Extending a dictionary*) |
| Check against the book without translating | `python app.py dict review books/MyBook.epub --dic books/MyBook.dic` → `MyBook.reviewed.dic` + report |
| Another target language | `python app.py dict convert books/MyBook.dic fr es zh` |
| Check a finished translation | `python app.py audit books/MyBook_ru.epub --dic books/MyBook_ru.dic --lang russian` |
| Explicit dictionary path | by default the `.dic` is looked up next to the book; `DICTIONARY=path/to/file.dic` in `.env` or `--dictionary path/to/file.dic` (the CLI flag wins) uses another file, e.g. a shared series dictionary — both pipelines, a missing file is created at that path (its directory must exist) |

---

## File Format (CSV with commas)

**Format:** `source = target, category, gender, notes`

```dic
# Vocabulary for AliceInWonderland
# Format: source = target, category, gender, notes

# PERSON (3 terms)
Alice = Алиса, PERSON, she, Main character, curious girl
Mad Hatter = Шляпный Болван, PERSON, he, Eccentric tea party host
Cheshire Cat = Чеширский Кот, PERSON, it, Mysterious grinning cat

# LOC (2 terms)
Wonderland = Страна Чудес, LOC, , 
Rabbit Hole = Кроличья Нора, LOC, , 

# ORG (1 term)
Queen's Court = Двор Королевы, ORG, , 
```

---

## Entry Structure

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| **source** | ✅ | string | Term in source language | `Alice` |
| **target** | ✅ | string | Translation | `Алиса` |
| **category** | ⚪ | string | Entity type | `PERSON`, `LOC`, `ORG`, `TERM` |
| **gender** | ⚪ | string | Gender for characters | `he`, `she`, `it`, `they` |
| **notes** | ⚪ | string | User comments | `Main character` |

**Format details:**
- Fields separated by **commas** (not pipes or JSON)
- Format: `source = target, category, gender, notes`
- Empty fields allowed: `term = перевод, LOC, , ` (empty gender and notes)
- Comments start with `#`
- Categories grouped with headers: `# PERSON (3 terms)`

---

## Categories

| Category | Description | Examples |
|----------|-------------|----------|
| **PERSON** | Character names | `Alice`, `Mad Hatter`, `Harry Potter` |
| **LOC** | Geographic locations | `Wonderland`, `Hogwarts`, `London` |
| **ORG** | Organizations | `Queen's Court`, `Ministry of Magic` |
| **TERM** | Domain-specific terms | `Quidditch`, `Portkey`, `Time Turner` |

**The category changes the translation.** Only `PERSON` has behaviour of its
own: its gender goes into the `<characters>` block of every stage, the GENDER
stage enforces it, the synopsis fills it in, the audit reports it when empty.
`LOC`, `ORG` and `TERM` are plain glossary entries (source → translation,
no gender). Where to put what:

| The entry is | Category |
|---|---|
| a named character, even a non-human one (a gender is needed: `he`/`she`/`it`/`they`) | `PERSON` |
| a race, species, people (`Prador`, `Jain`), a title, a technology, a coined word | `TERM` |
| a planet, city, country, region, building | `LOC` |
| an organization, a company, a fleet | `ORG` |

A race or a title as `PERSON` gets a gender and the GENDER stage makes the
sentences agree with it — wrong for a name of a kind. Moving an entry from
`PERSON` to another category: clear its gender. NER labels are folded into
these four when a dictionary is built (`GPE`/`FAC` → `LOC`; `NORP`, `MISC`,
`PRODUCT`, `EVENT` → `TERM`); the loader reads any category as written, but
only these four mean something to the pipeline.

---

## Gender Values

| Value | Usage |
|-------|-------|
| `he` | Male characters |
| `she` | Female characters |
| `it` | Animals, objects, neuter |
| `they` | Plural or non-binary |
| *(empty)* | Not applicable (LOC, ORG, TERM) |

The loader also accepts the usual spellings and turns them into these four:
`male`/`m`/`он`/`м`/`муж` → `he`, `female`/`f`/`она`/`ж`/`жен` → `she`, `оно`/`n`
→ `it`, `они`/`pl` → `they` (`src/gender_check.py`, `GENDER_SYNONYMS`). Any
other value is ignored with a warning in the log: the character then has no
gender, and the synopsis may fill it in. The gender of a PERSON goes to the
`<characters>` block of every stage ("Вашти — она (сказала)") and is checked
in the translation by the GENDER stage — a wrong gender here is enforced
throughout the book.

The categories and genders are checked against the book before every
translation — see [Dictionary check before a translation](#dictionary-check-before-a-translation).

---

## Examples

### Minimal (only required fields)
```dic
Alice = Алиса, PERSON, , 
```

### Full (all fields)
```dic
Alice = Алиса, PERSON, she, Main character, protagonist
```

### Multiple categories
```dic
# PERSON (2 terms)
Harry = Гарри, PERSON, he, Boy wizard
Hermione = Гермиона, PERSON, she, Smart witch

# LOC (1 term)
Hogwarts = Хогвартс, LOC, , Magic school

# TERM (2 terms)
Quidditch = Квиддич, TERM, , Wizard sport
Muggle = Магл, TERM, , Non-magic person
```

---

## Creating Dictionary

### Method 1: Automatic (NER)

```bash
# .env
NER=true
NERMODEL=en_core_web_lg

# Run translation
python app.py
# Vocabulary created: books/ExampleBook.dic
# Please review and restart.
```

**Process:**
1. NER of the source language finds the names and named things. One entry per
   entity: its forms are grouped by lemma ("Анну", "Анне" → "Анна", in the
   nominative when the book has it), the category is the one most mentions
   got ("Trike" tagged ORG 256 times and PERSON twice is one entry). Every
   label family is understood: OntoNotes (en, ja, zh), WikiNER `PER/LOC/ORG/MISC`
   (de, fr, es, it, pt, ru, uk, xx), Polish `persName/placeName/orgName`,
   Korean `PS/LC/OG`. Peoples, species and other named things
   (`NORP`, `MISC`, `PRODUCT`, `EVENT`: Prador, Jain) become TERM.
2. The LLM (proofread) **only translates**; the category goes to it as a hint
   ("Trike [ORG]": a name is transliterated, a coined word is not).
3. The categories and genders are decided by the book, like the
   [check before a translation](#dictionary-check-before-a-translation), and
   written into the new file:
   - an entry the book keeps calling *he* or *she* is a PERSON with that
     gender, whatever NER tagged it; a lowercase word NER took for a name
     ("dell", "submind") is a TERM;
   - the gender of a person: a form of address in the entry or before the
     name in the book ("Miss Raby", "Mr. Michael", "Signora", "мисс",
     "Frau", ...) decides; else the pronouns of the sentences naming only
     that person; when they disagree ("Miss Harbottle" once, "he" around her
     — another man) or are too few, the gender stays **empty** and is
     listed in `<book>.dictcheck.txt`. A wrong gender is worse than none: the
     translation follows the `.dic`, an empty one the synopsis fills in.
4. The new dictionary stops the run for your review: check the report, fill
   in the empty genders you know.
5. Restart translation.

### Method 2: Manual

Create `.dic` file manually:

```dic
# Vocabulary for MyBook
# Format: source = target, category, gender, notes

# PERSON (1 terms)
John = Джон, PERSON, he, Protagonist

# LOC (1 terms)
New York = Нью-Йорк, LOC, , 
```

### Method 3: Series dictionary (`--build-series-dict`)

Create a unified dictionary for a series of books to keep terminology
consistent across all volumes:

```bash
# Basic usage
python app.py --build-series-dict books/ --series-dict-output series.dic

# With custom thresholds
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --frequent-words --min-count-word 5
```

**Parameters:**
- `--build-series-dict` — path to the folder containing FB2/EPUB/TXT books
- `--series-dict-output` — output dictionary file (default: `series.dic`)
- `--min-count-ner` — minimum occurrences for NER entities (default: 2)
- `--frequent-words` — also add frequent ordinary words, not only named entities (default: off, `DICT_FREQUENT_WORDS`)
- `--min-count-word` — minimum occurrences for common words with `--frequent-words` (default: 5)

A dictionary for a single book can be built with `--build-dict path/to/book`.

**Workflow:** find all book files → extract text → NER (one entry per entity,
forms grouped by lemma, the category most mentions got) → aggregate counts
across all books → filter by thresholds → translate the terms via the
proofread LLM (it only translates; genders are set by the check before each
book's translation) → save the unified `.dic` file. Proper names keep their
capitalization and all their words (`John Smith`). The result is a regular
`.dic` file (`source = target, category, gender, notes`).

---

## Using Dictionary

Dictionary is automatically loaded if `.dic` file exists:

```bash
# Translation with dictionary
python app.py
# Vocabulary loaded: 15 entries
```

**Format in prompts:**
```
<vocabulary>
Alice = Алиса, PERSON, she
Wonderland = Страна Чудес, LOC, 
</vocabulary>
```

**Multi-word terms and substitution:**
- A term of more words wins over the shorter ones it contains: with `Hatter = Шляпник` and `Mad Hatter = Безумный Шляпник`, the text "Mad Hatter" is translated by the second entry, and `Hatter` is not put into the prompt for a chunk where it occurs only inside it. Then the longer term wins.
- Before the first stage the translations of the terms found in the chunk are substituted into the source text (the later stages see the original). Tags, links and URLs are never changed.
- Case: a lowercase source (`spidergun`) matches in any case; a source with capitals (`Will`) matches as written or in ALL CAPS, so it does not replace "will".
- For Korean, write names without the particle (`철수`, not `철수는`): the term is searched as a substring and matches every form.

Details: [NER_GUIDE.md](NER_GUIDE.md#-lexical-matching-stage-1).

---

## Dictionary rules during a run

- **Character genders** (`he`, `she`, `it`, `they`): every stage gets them
  written the target language's way (`Вашти — она (сказала)`), and the GENDER
  stage fixes sentences that contradict the dictionary. A gender in the file
  is never overwritten by a run; the synopsis fills in only empty ones, when
  two chunks agree.
- **Coined words:** besides characters, the synopsis stage reports invented
  words with no ordinary translation (`spidergun`); they are added as `TERM`.
  Words the spaCy model already knows are dropped.
- **No duplicates:** a candidate the dictionary already covers is not added —
  another case or inflected form of an entry (`Jain nodes` = `Jain node`,
  `Gabbleducks` = `gabbleduck`; a name only by inflection: `Jains` = `Jain`,
  but `Marie` ≠ `Mary`) or a phrase containing a known term (`Jain node`,
  `Jain-tech` when `Jain` is there). A hyphen, a space or no separator make
  different entries (`gabble-duck` ≠ `gabbleduck`); an ALL-CAPS acronym
  matches only itself (`ECS` ≠ `EC`).
- **Where found entries go:** new names and terms join the in-memory
  dictionary at once — the following chunks of the run use them, and a resumed
  run restores them from the checkpoint. They are written to the `.dic` only
  with `DICT_AUTO_SAVE=true` (default `false`: the reviewed dictionary stays
  as it is).
- **Term matching** (the same for every format): only the dictionary terms
  found in a chunk go into its prompt. Inflected forms are found (`spidergun`
  → `spiderguns`, `wolf` → `wolves`), Chinese/Japanese/Korean terms are matched
  as substrings, and a term never matches inside another word (`Ann` / `Annoying`).
- **A good dictionary after a fast pass:** run `FAST_TRANS=true` with
  `DICT_AUTO_SAVE=true` — the synopsis stage still runs in fast mode, so new
  names and terms are appended to the `.dic`; review it, then re-translate
  with `FAST_TRANS=false` and `--fresh`.

---

## Editing Dictionary

### Add new term
```dic
# Before
Alice = Алиса, PERSON, she, 

# After
Alice = Алиса, PERSON, she, Main character
White Rabbit = Белый Кролик, PERSON, he, Nervous rabbit
```

### Fix translation
```dic
# Before
Mad Hatter = Шляпник, PERSON, he, 

# After (more accurate)
Mad Hatter = Шляпный Болван, PERSON, he, Eccentric character
```

### Add gender
```dic
# Before
Cat = Кот, PERSON, , 

# After
Cat = Кот, PERSON, it, Cheshire Cat
```

---

## Dictionary check before a translation

Every translation run (both pipelines) checks the dictionary against the
source book right after loading it, before the first chunk — without an LLM,
with the spaCy model of the source language (`NERMODEL`, by `SOURCE_LANG`):

- **Category** by the NER labels of the entry's mentions in the book: a
  village written as PERSON becomes LOC/ORG, a species written lowercase in
  the `.dic` and in the book becomes TERM, a TERM the book treats as a
  person becomes PERSON. A character the book keeps calling *he* or *she*
  stays a person whatever NER says (it tags invented names ORG). A lowercase
  word is not a mention of a capitalized name ("stone" is not "Stone").
- **Gender** of a character by the 3rd person singular pronouns of the
  sentences that name only that character: an empty gender is filled in, a
  gender the book contradicts is changed. A decision needs more than three
  pronouns (4) and 85 % of them for one gender — in a scene of two ("she" in
  a sentence about Kuno is often Vashti) the gender stays unsure and is only
  reported.
- **A translation written in two alphabets** (`Gород`) is reported.

What happens with the findings:

| Setting | Sure findings | The run |
|---|---|---|
| default (`DICT_AUTOFIX=true`) | applied **for this run** in memory; the `.dic` is not changed, `<dic>.reviewed.dic` gets them to take over (a series dictionary: `<dic>.<book>.reviewed.dic`, one per book) | goes on |
| `--no-autofix` (`DICT_AUTOFIX=false`) | not applied | goes on as is (`DICT_FORCE=true`, the default) |
| `--no-autofix` with `DICT_FORCE=false` | not applied | stops (exit code 2) when the dictionary contradicts the book: a category or a gender the book contradicts, a translation in two alphabets; filling an empty category or gender does not stop it |
| a dictionary just built (`--build-dict` or a missing `.dic`) | written into the new file, it stops for review anyway | stops for review |

The report with all the evidence (also the unsure findings and the
characters not found in this book — normal for a series dictionary) is
`<book>.dictcheck.txt` next to the book. The result is cached in
`<book>.dictcheck.json` for this dictionary and book: a resumed run, or one
after editing a category or gender, does not parse the book again. A new or
removed entry (a manual edit, `DICT_AUTO_SAVE`) parses the whole book again —
minutes for a long book with a `*_lg` model on CPU. `DICT_CHECK=false` turns
the check off.

Languages: the NER labels of the spaCy models (OntoNotes `PERSON/GPE/ORG`,
WikiNER `PER/LOC/ORG`, Polish `persName/placeName/orgName`, Korean
`PS/LC/OG`) and the pronoun gender of their morphology (`Person=3` or
`Person=Third`) are understood; Chinese, Japanese and Korean pronouns have
no gender feature and are read by their form (他/她, 彼/彼女, 그/그녀). A model
without a parser (`xx_ent_wiki_sm`) gets a sentencizer; without a model the
check is skipped with a warning.

### Extending a dictionary with new books

A good series dictionary is not rebuilt for the next volume or for a new group
of books of the same universe: `dict extend` adds what it lacks and keeps the rest.

```bash
python app.py dict extend series.dic --book vol3.epub --book vol4.epub   # or --books-dir books/new/
python app.py dict extend series.dic --merge other-series.dic            # entries of another dictionary
```

- the result is a folder (`-o`, default `series.extended/`) with `series.dic` and
  `series.extend.report.txt`; the source `.dic` is not changed and its lines are
  copied as they are; the new entries follow under one dated comment
  `# new words 2026-10-18 (vol3.epub)`, by category - every extension leaves its own
  block at the end of the file, so the lines it added are easy to find;
- new entries: NER over the plain text of all the new books together (no markup) (`--min-count-ner`, default 3),
  translated by the proofread LLM; the category and the gender come from the
  books (as in `dict review`), not from the LLM;
- never an entry: one the dictionary already has (another case or form, or the
  same translated name of a character), a phrase containing a known term, an
  ordinary word, whatever the order of the lines (the shorter term first); a merged entry with another translation than the
  dictionary's is a conflict - the dictionary's translation stays;
- base lines change only as `dict review` would change them: an empty gender the
  books show clearly is set (a category too, when review is sure). A gender the books
  contradict, an unsure gender, duplicates, ordinary words and cut variants
  of the base are only reported;
- the log lists what needs a decision first (conflicts, unsure genders and categories,
  words in two alphabets, one translation for several entries, characters left without a
  gender), then what was added, changed and skipped and why. The files are written
  only after every step succeeded.

### A dictionary shared by a series

One `series.dic` for all books of a series (`DICTIONARY=series.dic` or
`--dictionary`) is **never changed by a translation run**:

- the check before each book reads it and fixes it **in memory for that
  book's run** only, against that book's text (a character of book 3 may not
  appear in book 1: "not found in the book" is normal and changes nothing);
  its findings go to `series.<book>.reviewed.dic` and `<book>.dictcheck.txt`;
- the synopsis adds new characters and fills empty genders in memory for the
  run (and its resume); into `series.dic` only with `DICT_AUTO_SAVE=true` —
  new lines and empty genders, an existing value is never rewritten;
- the file changes when you edit it or take over a `series.<book>.reviewed.dic`.

So the next book starts from `series.dic` as you left it. To carry the
findings of a book over to the next ones, take its reviewed copy (or the lines
you agree with) into `series.dic`.

Step by step before translating or retranslating a series:

1. Back up the dictionary: `cp series.dic series.dic.bak`.
2. Clean it: `python app.py dict clean series.dic` — read the report, take over what you agree with.
3. Check it against every book, each into its own file: `python app.py dict review book1.epub --dic series.dic -o series.book1.reviewed.dic` (the same for book2, …). Take over what the books agree on; decide the rest by hand — the `gender conflict` and `gender not sure` sections first.
4. Fix by hand what no tool can: a female character whose name is a masculine noun in the target language (`Client` → `Клиентка`?), a species or a title marked PERSON (→ `TERM`), a gender that jumps between `it`/`he`/`they`.
5. Translate the books in series order with `DICTIONARY=series.dic`, `DICT_AUTO_SAVE=false`, `--fresh`. Before the first chunk the dictionary is checked against that book; the sure fixes apply to that run only.
6. After each book, before the next one: read the run report (*The translation disagrees with the dictionary*, *Genders filled in from the synopsis*, *Words in two alphabets*), `<book>.dictcheck.txt` and `series.<book>.reviewed.dic`, and take over what is right into `series.dic`. Compare with an older translation: `python app.py audit … --compare …`.

## Dictionary commands

All of them write next to their input and never change the input itself:

```bash
# duplicates (by lexicon.word_key), gender spellings, ordinary words, cut variants
python app.py dict clean books/MyBook.dic            # -> MyBook.clean.dic + report
# categories and genders against the book (what the check before a translation does)
python app.py dict review books/MyBook.epub --dic books/MyBook.dic   # -> MyBook.reviewed.dic + report
# the dictionary into other target languages (proofread LLM from .env)
python app.py dict convert books/MyBook.dic fr es zh # -> MyBook_fr.dic, ...
# a finished translation: words in two alphabets, gender errors, characters without gender
python app.py audit books/MyBook_ru.epub --dic books/MyBook_ru.dic --lang russian --json audit.json
# passages through the real pipeline with the .env models (A/B of prompts and settings)
python app.py eval books/MyBook.epub --dic books/MyBook_ru.dic --count 8 --out logs/eval/run.json
# Calibre markers out of a FB2/HTML file (what the Calibre pipeline does to every book)
python app.py clean-calibre book.fb2 --inplace
```

`python app.py <command> -h` lists the options of each.

## Common Mistakes

### ❌ Wrong: JSON format (not supported)
```json
[
  {"source": "Alice", "target": "Алиса"}
]
```

### ❌ Wrong: Pipe separator (not supported)
```dic
Alice = Алиса | PERSON | she | Main character
```

### ❌ Wrong: Missing equals sign
```dic
Alice, Алиса, PERSON, she
```

### ✅ Correct: CSV with commas
```dic
Alice = Алиса, PERSON, she, Main character
```

---

## Technical Details

All reading and writing of `.dic` files goes through
`src/vocabulary_manager.py` (`VocabularyManager`) for every input format:

- `_load_from_file()` — parses `source = target, category, gender, notes`
  (the part after `=` with `csv.reader`, so quoted values may contain commas).
- `_parse_and_append_chunk()` — writes LLM-translated terms with CSV quoting.
- `apply_dictionary_candidates()` — writes what the synopsis stage reported: fills in genders, appends new named characters (PERSON) and coined terms (TERM, e.g. `spidergun`).

---

## spaCy models and languages

The dictionary is built and checked with the spaCy model of the **source**
language (`NERMODEL`, chosen by `SOURCE_LANG`):
`python -m spacy download en_core_web_lg` (English), `ru_core_news_lg`,
`de_core_news_lg`, `fr_core_news_lg`, `es_core_news_lg`, `it_core_news_lg`,
`pt_core_news_lg`, `pl_core_news_lg`, `uk_core_news_lg`, `ko_core_news_lg`,
`ja_core_news_lg`, `zh_core_web_lg`; any other language uses `xx_ent_wiki_sm`
(names only, no genders from pronouns).

- The gender check of the **translation** (GENDER stage) needs the model of
  the target language (`ru_core_news_sm`, `pl_core_news_sm`,
  `fr_core_news_sm`, …).
- Chinese, Japanese and Korean pronoun genders are read by their form.
- A book in a language without gendered pronouns (Turkish, Finnish,
  Hungarian) gives no genders — set them by hand.

Full per-language verification status: [LANGUAGES.md](LANGUAGES.md).

---

## GPU (CUDA) and CPU nuances of dictionary work

NER (dictionary creation) and the dictionary check run on **spaCy/PyTorch**,
so the GPU/CPU choice is theirs, not the LLM's:

- **CPU (default, works everywhere):** `pip install -e .` installs spaCy and
  the PyPI torch wheel; dictionary building and checking are slower on CPU
  (a full-book check with an `*_lg` model takes minutes — the result is
  cached in `<book>.dictcheck.json`, so a resumed run does not reparse).
- **GPU (CUDA 12.x):** add the cupy extra — `pip install -e ".[gpu]"`
  (`cupy-cuda12x==14.1.1`). spaCy picks up whichever cupy is importable and
  runs NER on the GPU. The GPU Docker image (`Dockerfile`,
  `nvidia/cuda`-based) ships it already; `Dockerfile.cpu` deliberately does
  not install cupy. `spacy[cuda12x]` is not used: its `cupy<13` pin conflicts
  with the pinned cupy 14 (see the comments in `pyproject.toml`).
- **Choosing/hiding the GPU for spaCy/PyTorch:** `CUDA_VISIBLE_DEVICES=0`
  selects a GPU; `CUDA_VISIBLE_DEVICES=` (empty) forces CPU even on a GPU
  host — handy when the GPU is busy serving the LLMs.
- **GPU Docker requirements:** NVIDIA driver 525.60+ (CUDA 12 compatible) and
  NVIDIA Container Toolkit; details in [GPU_DOCKER.md](GPU_DOCKER.md),
  troubleshooting in [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md).

---

## CJK sources (Korean, Japanese, Chinese)

Books can be translated directly from CJK languages into any language, with a
dictionary:

- **NER:** `ko_core_news_lg` uses its own KLUE label scheme (`PS`/`LC`/`OG`) —
  it is recognized and normalized to `PERSON`/`LOC`/`ORG`.
- **Dictionary matching:** CJK terms are found as substrings — there are no
  spaces between words, and Korean particles are glued to nouns (`철수는`).
- **Models:** `python -m spacy download ko_core_news_lg` (nothing extra),
  `ja_core_news_lg` and `zh_core_web_lg` need their tokenizers:
  `pip install -e ".[cjk]"`.
- **Korean particles:** entities are written to the dictionary without the
  glued particle (`철수는` → `철수`, `서울에서` → `서울`), so a term matches
  every form of the word. Because of the substring search a short name also
  matches inside a longer one (`철수` in `김철수`) — check such terms in the
  generated `.dic`.
- **Priority:** the longest term wins (`魔王城` over `魔王`); a Latin term
  inside CJK text (`ABC社`, full-width `ＡＢＣ` too) is substituted as a word
  of its own.
- **Frequent words** (only with `DICT_FREQUENT_WORDS=true`): minimum word
  length is 2 characters instead of 5 (a CJK word is usually 1-3 characters).
- **Length check:** a CJK text grows 2-4x in characters when translated into
  alphabetic languages. The expected ratio is learned from the book itself —
  the median of accepted chunks; the first 3 chunks are only checked for gross
  failures (×0.25 … ×5).

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

---

## Related Documentation

- [NER_GUIDE.md](NER_GUIDE.md) — Named Entity Recognition for vocabulary extraction
- [PROMPTS_GUIDE.md](PROMPTS_GUIDE.md) — How vocabulary is used in prompts
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — The 5-stage pipeline and the GENDER stage
- [LANGUAGES.md](LANGUAGES.md) — Per-language verification status
- [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md), [GPU_DOCKER.md](GPU_DOCKER.md) — CPU/GPU (CUDA) images
- [INSTALLATION.md](INSTALLATION.md) — Setup and configuration

---

**Changelog:**
- **2026-03-30:** Fixed format documentation (was incorrectly described as JSON)
- **v1.0:** Initial CSV format specification

**See also:** [books/eternal-moment.pg.dic](../books/eternal-moment.pg.dic) — Example dictionary file
