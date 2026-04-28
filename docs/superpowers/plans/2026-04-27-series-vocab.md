# Series Vocabulary Builder Implementation Plan

**Goal:** Add standalone function to create unified dictionary from multiple books in a series

**Architecture:** Standalone function in `src/ner.py` integrated via CLI in `app.py`. Processes all books in folder, aggregates NER results, translates via LLM, outputs JSON `.dic` file.

**Tech Stack:** Python, spaCy NER, existing fb2_handler/epub_handler/txt_handler, LLM translation

**Execution:** Use `subagent-driven-development` or `executing-plans` skill

---

## Task 0: Add helper function for file parsing

**Files:**
- Modify: `src/ner.py`

- [ ] **Step 1: Add helper to extract text from book file**
```python
def extract_text_from_book(book_path: str) -> str:
    """
    Extract text content from book file.
    
    Args:
        book_path: Path to .fb2/.epub/.txt file
        
    Returns:
        Extracted text content
    """
    from pathlib import Path
    from src import fb2_handler, epub_handler, txt_handler
    
    ext = Path(book_path).suffix.lower()
    if ext == '.fb2':
        body, header, footer = fb2_handler.parse_xml(book_path)
        return body
    elif ext == '.epub':
        body, header, footer = epub_handler.parse_epub(book_path)
        return body
    elif ext == '.txt':
        body, header, footer = txt_handler.parse_txt(book_path)
        return body
    else:
        raise ValueError(f"Unsupported file format: {ext}")
```

- [ ] **Step 2: Test helper function**
```bash
cd ~/prj/sunny-narrator && python -c "from src.ner import extract_text_from_book; print(len(extract_text_from_book('books/Cargo.fb2')))"
```
Expected: Number > 0

- [ ] **Step 3: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/ner.py && git commit -m "feat: add extract_text_from_book helper"
```

---

## Task 1: Implement `create_series_vocab()` function

**Files:**
- Modify: `src/ner.py` (append at end)

- [ ] **Step 1: Write the function skeleton**
```python
def create_series_vocab(
    books_folder: str,
    output_file: str = "series.dic",
    min_count_ner: int = 5,
    min_count_word: int = 10,
    min_word_length: int = 5
) -> str:
    """
    Create unified dictionary from all books in folder.
    
    Workflow:
    1. Find all .fb2/.epub/.txt files in folder
    2. For each book: parse text → NER → collect terms
    3. Merge all terms into unified array (aggregate counts)
    4. Filter by min_count criteria
    5. Translate via LLM
    6. Save to JSON .dic file
    
    Args:
        books_folder: Path to folder containing books
        output_file: Output .dic file path
        min_count_ner: Minimum occurrences for NER entities
        min_count_word: Minimum occurrences for common words
        min_word_length: Minimum word length for common words
        
    Returns:
        Path to output file
    """
    import json
    import os
    from pathlib import Path
    from collections import Counter
    
    # TODO: Implementation
    pass
```

- [ ] **Step 2: Implement file discovery**
```python
    # Find all book files
    supported_exts = {'.fb2', '.epub', '.txt'}
    book_files = []
    for f in os.listdir(books_folder):
        if Path(f).suffix.lower() in supported_exts:
            book_files.append(os.path.join(books_folder, f))
    
    if not book_files:
        raise ValueError(f"No book files found in {books_folder}")
    
    print(f"Found {len(book_files)} books")
```

- [ ] **Step 3: Implement NER aggregation across books**
```python
    # Aggregate terms from all books
    all_entities = []  # [(text, label), ...]
    all_words = Counter()  # word -> count
    book_names = {}  # book_path -> book_name
    
    for book_path in book_files:
        book_name = Path(book_path).stem
        book_names[book_path] = book_name
        
        print(f"Processing: {book_name}")
        text = extract_text_from_book(book_path)
        
        # Run NER (reuse make_vocab logic structure)
        # Get entities and words from this book
        # ...
        
        # For now, aggregate raw results
        # TODO: integrate with existing make_vocab
```

- [ ] **Step 4: Run partial test (file discovery)**
```bash
cd ~/prj/sunny-narrator && python -c "
from src.ner import create_series_vocab
try:
    result = create_series_vocab('books/', 'test_output.dic')
    print(f'Result: {result}')
except NotImplementedError:
    print('Function not implemented yet - expected')
except Exception as e:
    print(f'Error: {e}')
"
```
Expected: "Function not implemented yet - expected"

- [ ] **Step 5: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/ner.py && git commit -m "feat: add create_series_vocab skeleton"
```

---

## Task 2: Complete NER aggregation logic

**Files:**
- Modify: `src/ner.py`

- [ ] **Step 1: Integrate with existing make_vocab**
```python
    # After file discovery, for each book:
    for book_path in book_files:
        book_name = Path(book_path).stem
        text = extract_text_from_book(book_path)
        
        # Use existing make_vocab to get structured results
        extracted = make_vocab(
            text,
            min_count_ner=min_count_ner,  # Lower threshold for aggregation
            min_count_word=min_count_word,
            min_word_length=min_word_length
        )
        
        if extracted:
            for line in extracted.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Parse: "Term (CATEGORY)" or just "term"
                match = re.match(r'^(.+?)\s*\(([^)]+)\)$', line)
                if match:
                    term = match.group(1).strip()
                    category = match.group(2).strip()
                    all_entities.append((term, category, book_name))
                else:
                    all_words[line] += 1
```

- [ ] **Step 2: Aggregate and filter**
```python
    # Aggregate entity counts
    entity_counts = Counter((term, cat) for term, cat, _ in all_entities)
    
    # Filter by min_count_ner (after aggregation across all books)
    filtered_entities = [
        (term, cat, count) 
        for (term, cat), count in entity_counts.items() 
        if count >= min_count_ner
    ]
    
    # Filter words by min_count_word
    filtered_words = [
        (word, count) 
        for word, count in all_words.items() 
        if count >= min_count_word and len(word) >= min_word_length
    ]
    
    print(f"Filtered entities: {len(filtered_entities)}")
    print(f"Filtered words: {len(filtered_words)}")
```

- [ ] **Step 3: Test aggregation**
```bash
cd ~/prj/sunny-narrator && python -c "
from src.ner import create_series_vocab
import os
# Just test file discovery and basic flow
os.makedirs('books/test_series', exist_ok=True)
# Copy sample books
import shutil
shutil.copy('books/Cargo.fb2', 'books/test_series/')
shutil.copy('books/ExampleBook.fb2', 'books/test_series/')
# This will fail at translation step but test aggregation
"
```

- [ ] **Step 4: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/ner.py && git commit -m "feat: implement NER aggregation in create_series_vocab"
```

---

## Task 3: Add LLM translation and JSON export

**Files:**
- Modify: `src/ner.py`

- [ ] **Step 1: Prepare terms for translation**
```python
    # Combine entities and words for translation
    terms_for_translation = []
    
    for term, category, count in filtered_entities:
        terms_for_translation.append(term)
    
    for word, count in filtered_words[:100]:  # Limit to top 100 words
        terms_for_translation.append(word)
    
    if not terms_for_translation:
        print("No terms to translate")
        return output_file
    
    terms_text = '\n'.join(terms_for_translation)
```

- [ ] **Step 2: Translate via LLM**
```python
    # Use existing vocabulary translation
    from src import utils as ta
    config = Config()
    
    vocab_translated = ta.vocabulary(
        config.source_lang,
        config.target_lang,
        terms_text,
        config.country,
        "Proofread"
    )
```

- [ ] **Step 3: Parse and save JSON**
```python
    # Parse translations
    translations = {}
    for line in vocab_translated.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            parts = line.split('=', 1)
            source = parts[0].strip()
            target = parts[1].strip()
            translations[source.lower()] = target
    
    # Build final vocabulary list
    vocab_list = []
    
    for term, category, count in filtered_entities:
        term_lower = term.lower()
        vocab_list.append({
            "source": term,
            "target": translations.get(term_lower, ""),
            "category": category,
            "gender": "",
            "notes": "",
            "book_origin": book_names.get([k for k, v in book_names.items() if Path(k).stem in term][0] if any(Path(k).stem in term for k in book_names) else "")
    })
    
    for word, count in filtered_words[:100]:
        word_lower = word.lower()
        vocab_list.append({
            "source": word,
            "target": translations.get(word_lower, ""),
            "category": "TERM",
            "gender": "",
            "notes": f"frequent word (count: {count})",
            "book_origin": ""
        })
    
    # Save to JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(vocab_list, f, ensure_ascii=False, indent=2)
    
    print(f"Dictionary saved to: {output_file}")
    return output_file
```

- [ ] **Step 4: Test full function**
```bash
cd ~/prj/sunny-narrator && python -c "
from src.ner import create_series_vocab
result = create_series_vocab('books/', 'series_test.dic')
print(f'Created: {result}')
"
```

- [ ] **Step 5: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/ner.py && git commit -m "feat: complete create_series_vocab with translation and JSON export"
```

---

## Task 4: Add CLI integration to app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add argparse arguments**
```python
# Add after existing parser.add_argument calls
parser.add_argument('--build-series-dict', type=str, 
                   help='Build unified dictionary from books folder')
parser.add_argument('--series-dict-output', type=str, default='series.dic',
                   help='Output file for series dictionary')
```

- [ ] **Step 2: Add CLI handler**
```python
# Add before if __name__ == '__main__':
def handle_series_dict(args):
    """Handle --build-series-dict argument."""
    from src.ner import create_series_vocab
    
    books_folder = args.build_series_dict
    output_file = args.series_dict_output
    
    print(f"Building series dictionary from: {books_folder}")
    print(f"Output: {output_file}")
    
    result = create_series_vocab(books_folder, output_file)
    print(f"Done: {result}")
```

- [ ] **Step 3: Add main handler in if __name__ == '__main__' block**
```python
    if args.build_series_dict:
        handle_series_dict(args)
        return
```

- [ ] **Step 4: Test CLI**
```bash
cd ~/prj/sunny-narrator && python app.py --build-series-dict books/ --series-dict-output test_series.dic
```

- [ ] **Step 5: Commit**
```bash
cd ~/prj/sunny-narrator && git add app.py && git commit -m "feat: add --build-series-dict CLI option"
```

---

## Task 5: End-to-end test

**Files:**
- Test: `tests/test_series_vocab.py` (create)

- [ ] **Step 1: Create test file**
```python
"""Tests for series vocabulary builder."""
import os
import tempfile
import shutil
from pathlib import Path

def test_create_series_vocab():
    """Test creating vocabulary from multiple books."""
    from src.ner import create_series_vocab
    
    # Create temp folder with test books
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy sample books
        shutil.copy('books/Cargo.fb2', tmpdir)
        shutil.copy('books/ExampleBook.fb2', tmpdir)
        
        output = os.path.join(tmpdir, 'test.dic')
        
        # Run function
        result = create_series_vocab(tmpdir, output)
        
        # Verify output exists
        assert os.path.exists(result)
        
        # Verify JSON is valid
        import json
        with open(result) as f:
            data = json.load(f)
        
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check structure
        for entry in data:
            assert 'source' in entry
            assert 'target' in entry
```

- [ ] **Step 2: Run test**
```bash
cd ~/prj/sunny-narrator && python -m pytest tests/test_series_vocab.py -v
```

- [ ] **Step 3: Commit**
```bash
cd ~/prj/sunny-narrator && git add tests/test_series_vocab.py && git commit -m "test: add series vocab builder tests"
```

---

## Summary

**Total: 5 tasks**

- Task 0: Helper function for book parsing
- Task 1: Function skeleton
- Task 2: NER aggregation logic
- Task 3: Translation and JSON export
- Task 4: CLI integration
- Task 5: End-to-end tests
