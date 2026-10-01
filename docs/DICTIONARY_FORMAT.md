# Dictionary Format (.dic file)

**Version:** 1.0 (CSV with commas)  
**Last Updated:** 2026-03-30  
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
1. NER extracts terms from source text
2. LLM translates terms
3. Dictionary saved in CSV format
4. Review and edit dictionary
5. Restart translation

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
- `apply_character_genders()` — fills in genders reported by the synopsis stage.

---

## Related Documentation

- [NER_GUIDE.md](NER_GUIDE.md) — Named Entity Recognition for vocabulary extraction
- [PROMPTS_GUIDE.md](PROMPTS_GUIDE.md) — How vocabulary is used in prompts
- [INSTALLATION.md](INSTALLATION.md) — Setup and configuration

---

**Changelog:**
- **2026-03-30:** Fixed format documentation (was incorrectly described as JSON)
- **v1.0:** Initial CSV format specification

**See also:** [books/Cargo.dic](../books/Cargo.dic) — Example dictionary file
