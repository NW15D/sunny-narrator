# Dictionary Format (.dic file)

**Version:** 1.0 (CSV with commas)  
**Last Updated:** 2026-10-02  
**Issue:** Format mismatch fixed (was incorrectly documented as JSON)

---

## Overview

The dictionary file (`*.dic`) ensures terminology consistency throughout translation. It contains:
- Character name translations
- Geographic locations
- Domain-specific terminology
- Gender information for correct pronoun usage

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
| **OTHER** | Other entities | `Galleon` (currency), `Owl` (animal) |

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
| `--no-autofix` (`DICT_AUTOFIX=false`) | not applied | stops (exit code 2) when the dictionary contradicts the book: a category, a gender the book contradicts, a translation in two alphabets |
| `--no-autofix --force` | not applied | goes on as is |
| a dictionary just built (`--build-dict` or a missing `.dic`) | written into the new file, it stops for review anyway | stops for review |

The report with all the evidence (also the unsure findings and the
characters not found in this book — normal for a series dictionary) is
`<book>.dictcheck.txt` next to the book. The result is cached in
`<book>.dictcheck.json` for this dictionary and book: a resumed run does not
parse the book again. `DICT_CHECK=false` turns the check off.

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

## Related Documentation

- [NER_GUIDE.md](NER_GUIDE.md) — Named Entity Recognition for vocabulary extraction
- [PROMPTS_GUIDE.md](PROMPTS_GUIDE.md) — How vocabulary is used in prompts
- [INSTALLATION.md](INSTALLATION.md) — Setup and configuration

---

**Changelog:**
- **2026-03-30:** Fixed format documentation (was incorrectly described as JSON)
- **v1.0:** Initial CSV format specification

**See also:** [books/eternal-moment.pg.dic](../books/eternal-moment.pg.dic) — Example dictionary file
