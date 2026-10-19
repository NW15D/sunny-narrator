# Working with Dictionaries (.dic files)

## Overview

The dictionary file (`*.dic`) ensures terminology consistency throughout translation. It contains:
- Character name translations
- Geographic locations
- Domain-specific terminology
- Gender information for correct pronoun usage

### Commands at a glance

| Task | Command / step |
|---|---|
| New book, no dictionary | `python app.py` (or `python app.py --build-dict books/MyBook.epub`) → `books/MyBook_ru.dic` + `books/MyBook_ru.dictcheck.txt` → fill in the empty genders you know → run again |
| Translate with a dictionary | `python app.py` — the check runs first; read `<book>.dictcheck.txt`, take `<dic>.reviewed.dic` if you agree |
| Strict mode | `python app.py --no-autofix` — by the `.dic` as it is; `DICT_FORCE=false` — stops on a contradiction (exit code 2) |
| Series of books | `python app.py --build-series-dict books/series/ --series-dict-output series.dic`, then each book with `--dictionary series.dic`; a run never changes `series.dic`, each book gets `series.<book>.reviewed.dic` |
| Clean a dictionary | `python app.py dict clean books/MyBook_ru.dic` → `MyBook_ru.clean.dic` + report (duplicates, gender spellings, ordinary words) |
| Next volume of a series / new books of the same universe | `python app.py dict extend series.dic --book vol3.epub` → `series.extended/series.dic` + `series.extend.report.txt`; the existing entries stay, the new ones follow under `# new words <date>` (see *Method 4*) |
| Check against the book without translating | `python app.py dict review books/MyBook.epub --dic books/MyBook_ru.dic` → `MyBook_ru.reviewed.dic` + report |
| Another target language | `python app.py dict convert books/MyBook_ru.dic fr es zh` |
| Check a finished translation | `python app.py audit books/MyBook_ru.epub --dic books/MyBook_ru.dic --lang russian` |
| Explicit dictionary path | by default the dictionary is `<book>_<lang>.dic` next to the book (`<lang>` — the ISO code of `TARGET_LANG`; one dictionary per target language, a `<book>.dic` without the code is not used); `DICTIONARY=path/to/file.dic` in `.env` or `--dictionary path/to/file.dic` (the CLI flag wins) uses another file, e.g. a shared series dictionary — both pipelines, a missing file is created at that path (its directory must exist) |

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
# Dictionary created at books/MyBook_ru.dic. Review it, then re-run to start translation.
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

### Method 4: Extending an existing dictionary (`dict extend`)

A good series dictionary is not rebuilt for the next volume, or for a new
group of books of the same author's universe: `dict extend` keeps every entry
it has and adds only what the new books (or other dictionaries) bring, so the
whole series keeps one terminology.

```bash
# the next volume(s)
python app.py dict extend series.dic --book vol3.epub --book vol4.epub
# a folder of new books
python app.py dict extend series.dic --books-dir books/new/
# the entries another dictionary of the same universe has and this one lacks
python app.py dict extend series.dic --merge other-series.dic
# all together, the result into a chosen folder
python app.py dict extend series.dic --books-dir books/new/ --merge other-series.dic -o books/series-v2/
```

**Parameters:**
- `--book` — a new book (FB2/EPUB/TXT); repeatable
- `--books-dir` — a folder of new books (the reports the tools leave there are not taken for books)
- `--merge` — another `.dic` whose missing entries are added; repeatable
- `-o`, `--output-dir` — folder of the result (default: `<name>.extended/` next to the dictionary); it must not hold an input file
- `--min-count-ner` — mentions in all the new books together for an entity to be added (default: 3)
- `--frequent-words`, `--min-count-word` — also add frequent ordinary words (default: off; 5 mentions)
- `--keep` — comma-separated words not to skip as ordinary
- `--model` — spaCy model of the source language (default: `NERMODEL`)
- `--min-votes`, `--ratio` — evidence needed for a gender or a category, as in `dict review` (default: 4 and 0.85)

The languages and the proofread LLM come from `.env` (`SOURCE_LANG`,
`TARGET_LANG`, `COUNTRY`, `API_BASE_PROOFREAD`, …).

**The result** is a folder with two files:

- `series.dic` — the base file line by line as it was (comments included),
  then the new entries under one dated comment, by category:

  ```
  Vashti = Вашти, PERSON, she,
  ...
  # new words 2026-10-18 (vol3.epub)
  Bob = Боб,PERSON,he,
  Zork = Зорк,LOC,,
  ```

  Every extension leaves its own dated block at the end of the file, so the
  lines it added are easy to find (and to remove). Nothing to add — no block.
- `series.extend.report.txt` — the log: what needs a decision first, then what
  was done (see below).

The source `.dic` is never changed; both files are written only after every
step succeeded (an LLM error leaves no result).

**What becomes a new entry:**
1. NER over the plain text of all the new books together (no markup: a link or
   a tag is never taken for a name), the counts summed over the books.
2. Dropped, with the reason in the log: an entry the dictionary already has
   (another case or form: `vashti`, `Jains`; a character with the same translated
   name), a phrase containing a known term (`Jain node` when `Jain` is known —
   a separate entry would only shadow `Jain` with another translation), an
   ordinary word of the language. The same rules as for the candidates of the
   synopsis stage (`CandidateMatcher`), the shorter term first, so the order of
   the lines does not matter. A hyphen, a space or no separator make different
   entries (`Jain-tech` is not `Jain tech`).
3. The rest is translated by the proofread LLM; the LLM only translates.
4. The category and the gender come from the new books, as in `dict review`
   (pronouns, forms of address like `Miss`/`Mr`, NER labels); an unsure gender
   stays empty and goes to the log.

From `--merge`: an entry the base lacks is added with its category, gender
and notes; one the base has with **another** translation is a conflict — the
base keeps its own translation, both go to the log.

**What happens to the base entries:** they are not rewritten. Only what
`dict review` would change against the new books: an **empty** gender the books
show clearly is set (a category too, when the review is sure). A gender the
books contradict is not changed — it is a conflict in the log. Duplicates,
ordinary words and cut variants in the base are reported, not removed (that is
`dict clean`'s job).

**The log** (`<name>.extend.report.txt`), in this order:
- to decide: `merge: conflict`, `… gender conflict`, `… category: not sure`,
  `… gender not sure`, `check: translation in two alphabets`, `check: one translation
  for several entries`, `check: translation equals the source`, `check: person without
  a gender`, suspicious lines of the base, terms the LLM did not translate;
- done: `… gender set`, `… category changed`, `added from books`, `added from dictionaries`;
- skipped: `already in the dictionary`, `covered by existing terms`, `ordinary word`,
  `same by the translated name`; then the characters without a gender the new books never mention.

`base:` / `merged:` / `new:` before a section tell whose lines it lists.

---

## Using Dictionary

The dictionary `<book>_<lang>.dic` next to the book (`books/MyBook.epub`, `TARGET_LANG=ru` → `books/MyBook_ru.dic`) is loaded automatically; without it the first run builds it there and stops for review:

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
- Before the first stage the translations of the names (`PERSON`, `LOC`, `ORG`) and of the multi-word terms found in the chunk are substituted into the source text (the later stages see the original). A one-word `TERM` (`Variedad`, `Seguro`) is not: its base form inside a sentence of the source language breaks the grammar (`La вариант`), so the model gets it from the glossary of the prompt and inflects it itself. Tags, links and URLs are never changed.
- Case: a lowercase source (`spidergun`) matches in any case; a source with capitals (`Will`) matches as written or in ALL CAPS, so it does not replace "will".
- For Korean, write names without the particle (`철수`, not `철수는`): the term is searched as a substring and matches every form.

Details: [NER_GUIDE.md](NER_GUIDE.md#lexical-matching-stage-1).

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

0. A new volume, or new books of the same universe: `python app.py dict extend series.dic --book vol3.epub` — read `series.extended/series.extend.report.txt` (the sections to decide come first), fix what you disagree with in `series.extended/series.dic` and take it over as `series.dic` (*Method 4*).
1. Back up the dictionary: `cp series.dic series.dic.bak`.
2. Clean it: `python app.py dict clean series.dic` — read the report, take over what you agree with.
3. Check it against every book, each into its own file: `python app.py dict review book1.epub --dic series.dic -o series.book1.reviewed.dic` (the same for book2, …). Take over what the books agree on; decide the rest by hand — the `gender conflict` and `gender not sure` sections first.
4. Fix by hand what no tool can: a female character whose name is a masculine noun in the target language (`Client` → `Клиентка`?), a species or a title marked PERSON (→ `TERM`), a gender that jumps between `it`/`he`/`they`.
5. Translate the books in series order with `DICTIONARY=series.dic`, `DICT_AUTO_SAVE=false`, `--fresh`. Before the first chunk the dictionary is checked against that book; the sure fixes apply to that run only.
6. After each book, before the next one: read the run report (*The translation disagrees with the dictionary*, *Genders filled in from the synopsis*, *Words in two alphabets*), `<book>.dictcheck.txt` and `series.<book>.reviewed.dic`, and take over what is right into `series.dic`. Compare with an older translation: `python app.py audit … --compare …`.

## Dictionary commands

All of them write next to their input (`dict extend` — into a folder next to it) and never change the input itself:

```bash
# duplicates (by lexicon.word_key), gender spellings, ordinary words, cut variants
python app.py dict clean books/MyBook_ru.dic            # -> MyBook_ru.clean.dic + report
# categories and genders against the book (what the check before a translation does)
python app.py dict review books/MyBook.epub --dic books/MyBook_ru.dic   # -> MyBook_ru.reviewed.dic + report
# the dictionary carried over to new books / dictionaries (into a folder, see Method 4)
python app.py dict extend series.dic --book vol3.epub [--merge other.dic]   # -> series.extended/
# the dictionary into other target languages (proofread LLM from .env)
python app.py dict convert books/MyBook_ru.dic fr es zh # -> MyBook_fr.dic, ... (the name a run looks up)
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

NER (dictionary creation) and the dictionary check run on **spaCy** (thinc:
NumPy on the CPU, CuPy on the GPU), so the GPU/CPU choice is theirs, not the
LLM's:

- **CPU (default, works everywhere):** `pip install -e .` installs spaCy;
  dictionary building and checking are slower on CPU
  (a full-book check with an `*_lg` model takes minutes — the result is
  cached in `<book>.dictcheck.json`, so a resumed run does not reparse).
- **GPU (CUDA 12.x):** add the cupy extra — `pip install -e ".[gpu]"`
  (`cupy-cuda12x==14.1.1`). spaCy picks up whichever cupy is importable and
  runs NER on the GPU. What runs there: NER and word vectors of `--build-dict`,
  `--build-series-dict`, `dict clean`, `dict extend` (its NER) and the
  per-chunk term lookup. The check before a translation, `dict review` and the
  gender check of a translation load their model without asking for the GPU. Even on the GPU an
  `*_sm`/`*_lg` model keeps the GPU almost idle: tokenizing, the lemmatizer and
  the rules run on the CPU, only the small networks run on the GPU (a 150k-char
  book with `en_core_web_lg`: 4.9 s on CPU, 4.2 s on GPU). spaCy takes CUDA
  device 0, and CUDA numbers the GPUs **fastest first** - on a host with several
  GPUs that is not necessarily `nvidia-smi`'s GPU 0 (with a slower card at
  `nvidia-smi -i 0`, spaCy runs on the faster one at `-i 1`). `CUDA_DEVICE_ORDER=PCI_BUS_ID` makes both numberings the
  same; `CUDA_VISIBLE_DEVICES` then picks the GPU. No torch is involved: spaCy
  runs on thinc with CuPy.
- **Transformer models (`*_trf`):** `en_core_web_trf` 3.8 needs
  `spacy-curated-transformers>=0.2.2,<0.3` with `curated-transformers<0.2`
  (not `spacy-transformers`, and not the 2.x releases: they fail with `E002
  curated_transformer` or `load_state_dict: Missing key(s)`), plus
  `transformers` and `spacy-alignments`. It does use the GPU (2x faster than on
  the CPU, about 550 MB) but has **no word vectors**: the cosine stage of the
  term lookup finds nothing and `dict clean` / `dict extend` do not drop
  ordinary words. Russian has no `*_trf` model at all. The project does not
  install these packages. The GPU Docker image (`Dockerfile`,
  `nvidia/cuda`-based) ships it already; `Dockerfile.cpu` deliberately does
  not install cupy. `spacy[cuda12x]` is not used: its `cupy<13` pin conflicts
  with the pinned cupy 14 (see the comments in `pyproject.toml`).
- **Choosing/hiding the GPU for spaCy:** `CUDA_VISIBLE_DEVICES=0`
  selects a GPU; `CUDA_VISIBLE_DEVICES=` (empty) forces CPU even on a GPU
  host — handy when the GPU is busy serving the LLMs.
- **GPU Docker requirements:** NVIDIA driver 525.60+ (CUDA 12 compatible) and
  NVIDIA Container Toolkit; details in [DOCKER.md](DOCKER.md).

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
- [DOCKER.md](DOCKER.md) — the CPU and GPU (CUDA) images
- [INSTALLATION.md](INSTALLATION.md) — Setup and configuration

---

**Changelog:**
- **2026-03-30:** Fixed format documentation (was incorrectly described as JSON)
- **v1.0:** Initial CSV format specification

**See also:** [tests/data/eternal-moment.pg_fr.dic](../tests/data/eternal-moment.pg_fr.dic) — an example dictionary (English → French)
