# Series Vocabulary Builder Design

**Goal:** Create unified dictionary from multiple books in a series for consistent translation

## Architecture

Standalone function in `src/ner.py` integrated via CLI in `app.py`. Processes all books in folder, aggregates NER results, translates via LLM, outputs JSON `.dic` file.

## Components

### 1. New function: `create_series_vocab()` in `src/ner.py`

**Location:** `src/ner.py`

**Signature:**
```python
def create_series_vocab(
    books_folder: str,
    output_file: str = "series.dic",
    min_count_ner: int = 5,
    min_count_word: int = 10,
    min_word_length: int = 5
) -> str:
```

**Workflow:**
1. Find all `.fb2`/`.epub`/`.txt` files in folder
2. For each book: parse text → NER → collect terms
3. Merge all terms into unified array (aggregate counts across books)
4. Filter by min_count criteria
5. Translate via LLM
6. Save to JSON `.dic` file

**Returns:** Path to output file

### 2. CLI integration in `app.py`

**New arguments:**
```python
parser.add_argument('--build-series-dict', type=str, help='Build unified dictionary from books folder')
parser.add_argument('--series-dict-output', type=str, default='series.dic', help='Output file for series dictionary')
```

**Usage:**
```bash
python app.py --build-series-dict /path/to/books --output series.dic
```

### 3. Aggregation logic

- Parse each book → extract text using existing handlers (fb2_handler, epub_handler, txt_handler)
- Run NER per book (reuse `make_vocab` logic)
- Aggregate: `Counter[(text, label)]` — sum counts across all books
- Filter after aggregation: entities with total count >= min_count_ner, words >= min_count_word
- Single LLM call for translation of all aggregated terms

### 4. Output format

Same JSON `.dic` format as current:
```json
[
  {"source": "Alice", "target": "Алиса", "category": "PERSON", "gender": "", "notes": "", "book_origin": "Book1"},
  {"source": "wonderland", "target": "Страна чудес", "category": "TERM", "gender": "", "notes": "frequent word", "book_origin": ""},
  ...
]
```

Field `book_origin` indicates which book the term came from (useful for user review).

## Data Flow

```
books_folder/*.fb2
       │
       ▼
┌──────────────────┐
│ create_series_vocab │
│  1. Find files   │
│  2. Parse texts  │
│  3. Run NER      │
│  4. Aggregate    │
│  5. Filter       │
│  6. Translate    │
│  7. Save JSON    │
└──────────────────┘
       │
       ▼
   series.dic
```

## Testing Strategy

1. Unit test: aggregation logic (mock NER results)
2. Integration test: run on sample books folder
3. Verify output JSON matches schema from `vocabulary_manager.validate_dictionary()`

## Dependencies

- Existing: `src/ner.py`, `src/fb2_handler.py`, `src/epub_handler.py`, `src/txt_handler.py`, `src/utils.vocabulary()`
- New: None (reuse existing)
