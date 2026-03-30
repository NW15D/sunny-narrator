# Dictionary Format (.dic file) — JSON Format

**Version:** 2.0 (JSON)  
**Last Updated:** 2026-03-30

---

## Overview

The dictionary file (`*.dic`) ensures terminology consistency throughout translation. It contains:
- Character name translations
- Geographic locations
- Domain-specific terminology
- Gender information for correct pronoun usage

---

## File Format (JSON)

**New format (v2.0):**

```json
# Vocabulary for AliceInWonderland
# Format: JSON array of vocabulary entries
[
  {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she", "notes": "Main character, curious girl"},
  {"source": "Mad Hatter", "target": "Шляпный Болван", "category": "PERSON", "gender": "he", "notes": "Eccentric tea party host"},
  {"source": "Cheshire Cat", "target": "Чеширский Кот", "category": "PERSON", "gender": "it", "notes": "Mysterious, grinning cat"},
  {"source": "Wonderland", "target": "Страна Чудес", "category": "LOC", "gender": "", "notes": ""},
  {"source": "Rabbit Hole", "target": "Кроличья Нора", "category": "LOC", "gender": "", "notes": ""},
  {"source": "Queen's Court", "target": "Двор Королевы", "category": "ORG", "gender": "", "notes": ""}
]
```

---

## Entry Structure

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| **source** | ✅ | string | Term in source language | `"Alice"` |
| **target** | ✅ | string | Translation | `"Алиса"` |
| **category** | ⚪ | string | Entity type | `"PERSON"`, `"LOC"`, `"ORG"`, `"TERM"` |
| **gender** | ⚪ | string | Gender for characters | `"he"`, `"she"`, `"it"`, `"they"` |
| **notes** | ⚪ | string | User comments | `"Main character"` |

### JSON Schema

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": ["source", "target"],
    "properties": {
      "source": {"type": "string"},
      "target": {"type": "string"},
      "category": {"type": "string", "enum": ["PERSON", "LOC", "ORG", "TERM", "OTHER"]},
      "gender": {"type": "string", "enum": ["he", "she", "it", "they", ""]},
      "notes": {"type": "string"}
    }
  }
}
```

---

## Categories

| Category | Description | Examples |
|----------|-------------|----------|
| **PERSON** | People, characters | `{"source": "Alice", "category": "PERSON"}` |
| **LOC** | Locations, places | `{"source": "Wonderland", "category": "LOC"}` |
| **ORG** | Organizations, groups | `{"source": "Queen's Court", "category": "ORG"}` |
| **TERM** | Domain-specific terms | `{"source": "Portals", "category": "TERM"}` |
| **OTHER** | Default/uncategorized | `{"source": "item", "category": "OTHER"}` |

**Default:** If `category` is omitted, defaults to `"TERM"`.

---

## Gender

Gender is used for:
1. Correct pronouns in translation (he/she/it → он/она/оно)
2. Character tracking in SynopsisManager
3. Consistency across chunks

### Values

| Value | Description | Pronouns (EN) | Pronouns (RU) |
|-------|-------------|---------------|---------------|
| `he` | Male | he, his, him | он, его, ему |
| `she` | Female | she, her, hers | она, её, ей |
| `it` | Inanimate/object | it, its | оно, его |
| `they` | Plural/unspecified | they, their, them | они, их, им |
| `""` | Not specified | — | — |

### Determining Gender

1. **From text:** LLM infers gender from pronouns near the name
2. **From dictionary:** User specifies manually in `.dic`
3. **Default:** PERSON without gender → not tracked

---

## Legacy Format Support

**Old format (v1.0) is still supported for reading:**

```
# Vocabulary for BookName
# Format: source = target | category | gender | notes

Alice = Алиса | PERSON | she | Main character
Wonderland = Страна Чудес | LOC | | 
```

**On next save, legacy files are automatically converted to JSON.**

---

## Workflow

### 1. Dictionary Creation

**Automatic (NER):**
```bash
python app.py books/mybook.fb2
# NER extracts entities → creates mybook.dic
```

**Manual:**
```bash
# Create empty template
touch books/mybook.dic

# Edit with your terms
nano books/mybook.dic
```

### 2. Dictionary Editing

**Recommended editors:**
- VS Code (with JSON extension)
- jq (command-line JSON processor)
- Any text editor

**Example with jq:**
```bash
# Add new entry
jq '. += [{"source": "NewTerm", "target": "НовыйТермин", "category": "TERM"}]' books/mybook.dic > tmp && mv tmp books/mybook.dic

# Validate JSON
jq '.' books/mybook.dic > /dev/null && echo "Valid JSON"
```

### 3. Dictionary Usage

Dictionary is automatically loaded by `VocabularyManager`:

```python
from src.vocabulary_manager import VocabularyManager

manager = VocabularyManager(book_path="books/mybook.fb2")
vocab = manager.initialize()  # Loads or creates .dic

# Get vocabulary for chunk
chunk_vocab = manager.get_vocab_for_chunk(chunk_text, 0, 0)

# Format for model
formatted = manager.format_for_model(chunk_vocab, model="Hunyuan")
```

---

## Validation

### Built-in Validation

```python
from src.vocabulary_manager import validate_dictionary

# Validate dictionary file
errors = validate_dictionary("books/mybook.dic")
if errors:
    print("Validation errors:")
    for error in errors:
        print(f"  - {error}")
else:
    print("Dictionary is valid!")
```

### Manual Validation

**Using jq:**
```bash
# Check JSON syntax
jq '.' books/mybook.dic > /dev/null && echo "✓ Valid JSON"

# Check required fields
jq '.[] | select(.source == null or .target == null)' books/mybook.dic
# (empty output = all entries have source and target)

# Check categories
jq '.[].category' books/mybook.dic | sort | uniq -c
```

**Using Python:**
```python
import json

with open('books/mybook.dic') as f:
    # Skip comments
    content = ''.join(line for line in f if not line.startswith('#'))
    data = json.loads(content)

for i, entry in enumerate(data):
    assert 'source' in entry, f"Entry {i}: missing 'source'"
    assert 'target' in entry, f"Entry {i}: missing 'target'"
    assert entry['category'] in ['PERSON', 'LOC', 'ORG', 'TERM', 'OTHER', ''], \
        f"Entry {i}: invalid category '{entry['category']}'"
    assert entry['gender'] in ['he', 'she', 'it', 'they', ''], \
        f"Entry {i}: invalid gender '{entry['gender']}'"
```

---

## Migration from Legacy Format

**Automatic:**
- Legacy `.dic` files load automatically
- On next save, converted to JSON
- No manual action required

**Manual conversion:**
```bash
# Use provided script
python scripts/convert_dict_legacy_to_json.py books/oldbook.dic
```

**Example conversion:**

**Before (legacy):**
```
Alice = Алиса | PERSON | she | Main character
```

**After (JSON):**
```json
{"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she", "notes": "Main character"}
```

---

## Best Practices

### 1. Keep Dictionary Focused

**DO:**
- Add character names
- Add key locations
- Add domain-specific terms

**DON'T:**
- Add common words (the, a, is)
- Add every proper noun
- Over-populate (>500 terms may slow down)

### 2. Use Consistent Categories

```json
// ✅ Good
{"source": "Alice", "category": "PERSON"}
{"source": "Wonderland", "category": "LOC"}

// ❌ Inconsistent
{"source": "Alice", "category": "Character"}  // Should be PERSON
{"source": "Wonderland", "category": "Place"}  // Should be LOC
```

### 3. Fill Gender for Characters

```json
// ✅ Good - gender specified
{"source": "Alice", "category": "PERSON", "gender": "she"}
{"source": "Mad Hatter", "category": "PERSON", "gender": "he"}

// ❌ Missing gender (pronouns may be wrong)
{"source": "Alice", "category": "PERSON", "gender": ""}
```

### 4. Add Helpful Notes

```json
// ✅ Good notes
{"source": "Cheshire Cat", "target": "Чеширский Кот", 
 "notes": "Mysterious, grinning cat. Appears/disappears frequently."}

// ❌ Not helpful
{"source": "Cheshire Cat", "target": "Чеширский Кот", 
 "notes": "cat"}
```

---

## Troubleshooting

### Dictionary Not Loading

**Check:**
1. File exists: `ls books/*.dic`
2. Valid JSON: `jq '.' books/mybook.dic`
3. Correct encoding: `file -i books/mybook.dic` (should be `utf-8`)

### Terms Not Applied

**Check:**
1. Category matches: `jq '.[].category' books/mybook.dic`
2. Source text matches exactly (case-sensitive)
3. NER matching enabled: `grep NER .env`

### JSON Syntax Errors

**Common issues:**
- Missing comma between entries
- Unescaped quotes in notes
- Trailing comma after last entry

**Fix:**
```bash
# Validate and find line number
python3 -m json.tool books/mybook.dic 2>&1 | grep "line"
```

---

## Examples

### Minimal Dictionary

```json
[
  {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she"}
]
```

### Full Example

```json
# Vocabulary for AliceInWonderland
[
  {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "she", "notes": "Main character"},
  {"source": "Mad Hatter", "target": "Шляпный Болван", "category": "PERSON", "gender": "he", "notes": "Tea party host"},
  {"source": "Cheshire Cat", "target": "Чеширский Кот", "category": "PERSON", "gender": "it", "notes": "Grinning cat"},
  {"source": "White Rabbit", "target": "Белый Кролик", "category": "PERSON", "gender": "he", "notes": "Late for meeting"},
  {"source": "Queen of Hearts", "target": "Королева Червей", "category": "PERSON", "gender": "she", "notes": "Off with their heads!"},
  {"source": "Wonderland", "target": "Страна Чудес", "category": "LOC", "gender": "", "notes": "Main setting"},
  {"source": "Rabbit Hole", "target": "Кроличья Нора", "category": "LOC", "gender": "", "notes": "Entrance to Wonderland"},
  {"source": "Tea Party", "target": "Чаепитие", "category": "TERM", "gender": "", "notes": "Mad Hatter's endless tea party"},
  {"source": "Croquet", "target": "Крокет", "category": "TERM", "gender": "", "notes": "Game with flamingos as mallets"}
]
```

---

## See Also

- [NER_GUIDE.md](NER_GUIDE.md) — How NER extracts terms
- [VOCABULARY_REFACTOR_PLAN.md](VOCABULARY_REFACTOR_PLAN.md) — Vocabulary system design
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — How vocabulary is used in translation
