# Детальное ревью: Сборка словаря и косинусный поиск

**Дата:** 2026-05-07  
**Автор:** Dev  
**Проблема:** Слова из словаря (*.dic) не попадают в перевод чанка, даже если они есть в тексте

---

## 📋 Маршрут слова через систему

```
.dic файл → load_vocab_from_file() → vocab_manager.get_vocab_for_chunk()
          → find_matching_words_with_cosine_similarity() → format_for_model()
          → prompt injection → LLM translation
```

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### Problem #1: Косинусный поиск вместо текстового match

**Файл:** `src/ner.py`, функции `find_matching_words_with_cosine_similarity` (строка 415) и `find_matching_words_with_cosine_similarity_cpu` (строка 482)

**Суть:**  
Функция ищет семантически близкие слова через косинусное сходство векторов, но **НЕ проверяет точное наличие термина в тексте**.

**threshold=0.8** — это семантическая близость, не presence check.

**Пример бага:**
```python
# Словарь: {"bonded": "связанный", "hooder": "капюшонник"}
# Текст чанка: "The bonded soldier lifted his hooder weapon..."

# Косинусный поиск:
# - "bonded" в словаре → ищет семантически похожие токены
# - threshold=0.8 → может НЕ найти "bonded" из текста, если вектор слабо совпадает
# - Результат: слово не попадает в vocabulary для чанка
```

**Код (ner.py, строки 430-448):**
```python
# Строим векторы словаря
for phrase in orig_values:
    sub_words = phrase.split()  # ❌ BUG: split() для составных терминов
    sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
    sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]
    
    if sub_vecs:
        mean_vec = np.mean(np.vstack(sub_vecs), axis=0)  # ❌ Mean вектор теряет точность
        vocab_vectors.append(mean_vec)
        valid_vocab_words.append(phrase)

# Ищем в токенах чанка
sims = cp.dot(token_vectors, vocab_matrix.T)
best_matches = cp.where(sims > threshold)  # ❌ threshold не гарантирует match
```

**Корень проблемы:**
1. `phrase.split()` — разбивает составные термины ("John Smith" → ["John", "Smith"])
2. Mean вектор двух слов ≠ вектор фразы "John Smith"
3. Threshold=0.8 — слишком высокий для exact match
4. **Нет текстового search для точного наличия слова в чанке**

---

### Problem #2: Форматирование с лишними запятыми

**Файл:** `src/vocabulary_manager.py`, метод `_format_standard` (строка 511)

**Код:**
```python
def _format_standard(self, entries: List[VocabEntry]) -> str:
    lines = []
    for entry in entries:
        line = f"{entry.source} = {entry.target}"
        parts = []
        if entry.category:
            parts.append(entry.category)
        if entry.gender:
            parts.append(entry.gender)
        if entry.notes:
            parts.append(entry.notes)
        
        if parts:
            line += ", " + ", ".join(parts)  # ❌ Always adds ", " if parts exists
        
        lines.append(line)
    
    return "\n".join(lines)
```

**Результат (с лишними запятыми):**
```dic
crushed = раздавил,, ,
story = история,, ,
bonded = связанный,, ,
```

**Желаемый результат:**
```dic
crushed = раздавил
story = история
bonded = связанный
hooder = капюшонник,PERSON,он, инопланетное существо
```

---

### Problem #3: Fallback на полный словарь вместо chunk-specific

**Файл:** `app.py`, метод `get_formatted_vocab_for_chunk` (строка 79)

**Код:**
```python
if not entries:
    logger.warning(f"get_vocab_for_chunk returned 0 entries...")
    # Don't return empty - use full vocabulary if available
    if self.vocab_manager and self.vocab_manager.vocab:
        logger.info(f"Fallback: using full vocabulary ({len(self.vocab_manager.vocab)} entries)")
        entries = list(self.vocab_manager.vocab.values())  # ❌ Все слова подряд
```

**Проблема:**  
Если косинусный поиск вернул 0 matches, система падает на полный словарь. Но полный словарь может быть огромным (200+ терминов), что:
1. Забивает prompt
2. Уменьшает качество перевода
3. Токены wasted

---

## 🔧 РЕШЕНИЯ

### Solution #1: Добавить текстовый search ПЕРЕД косинусным

**Файл:** `src/ner.py`

**Новая логика:**
```python
def find_matching_words_with_cosine_similarity(text, vocab, lng, threshold=0.8, batch_size=1024):
    """
    Two-stage matching:
    1. TEXT SEARCH: Exact substring match for vocab terms in text
    2. COSINE SEARCH: Semantic similarity for unmatched terms (lower threshold)
    """
    
    matched_words_set = set()
    
    # Stage 1: TEXT SEARCH (exact match)
    # ====================================
    text_lower = text.lower()
    
    for entry_key, entry in vocab.items():
        source_term = entry.get(lng, "")
        if not source_term:
            continue
        
        # Check if term exists in text (case-insensitive)
        if source_term.lower() in text_lower:
            matched_words_set.add(source_term)
            logger.debug(f"Text match: '{source_term}' found in chunk")
    
    # Stage 2: COSINE SEARCH (semantic similarity for remaining terms)
    # ================================================================
    unmatched_vocab = {k: v for k, v in vocab.items() 
                       if v.get(lng, "") not in matched_words_set}
    
    if unmatched_vocab:
        # Use LOWER threshold for semantic matching (0.6 instead of 0.8)
        semantic_threshold = 0.6
        
        # ... existing cosine similarity logic for unmatched_vocab ...
        # Returns additional matches based on semantic similarity
```

**Ключевые изменения:**
1. **Stage 1 — Text Search:** Простой substring check (`term.lower() in text.lower()`)
2. **Stage 2 — Cosine Search:** Только для unmatched terms с threshold=0.6
3. **Log separation:** Разные log messages для text match и semantic match

---

### Solution #2: Улучшить форматирование без лишних запятых

**Файл:** `src/vocabulary_manager.py`

**Новый `_format_standard`:**
```python
def _format_standard(self, entries: List[VocabEntry]) -> str:
    """
    Format: source = target
    Additional fields added ONLY if they have content:
    - category, gender, notes (no trailing commas)
    """
    lines = []
    for entry in entries:
        line = f"{entry.source} = {entry.target}"
        
        # Build metadata string only if fields are present
        meta_parts = []
        if entry.category:
            meta_parts.append(entry.category)
        if entry.gender:
            meta_parts.append(entry.gender)
        if entry.notes:
            meta_parts.append(entry.notes)
        
        # Add metadata ONLY if non-empty
        if meta_parts:
            line += ", " + ", ".join(meta_parts)
        
        lines.append(line)
    
    return "\n".join(lines)
```

**Примеры вывода:**
```dic
bonded = связанный
hooder = капюшонник, PERSON, он, инопланетное существо
Alice = Алиса, PERSON, she
Wonderland = Страна Чудес, LOC
```

---

### Solution #3: Удалить fallback на полный словарь

**Файл:** `app.py`, метод `get_formatted_vocab_for_chunk`

**Изменение:**
```python
def get_formatted_vocab_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> str:
    entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
    
    if not entries:
        # NO FALLBACK - empty vocab is valid for chunks without dictionary terms
        logger.info(f"Chunk {s_idx}-{c_idx}: No matching vocabulary terms")
        return ""  # Return empty, not full vocab
    
    formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
    
    if config.debug:
        logger.debug(f"Vocab for chunk {s_idx}-{c_idx}: {len(entries)} terms")
    
    return formatted
```

**Обоснование:**
- Чанк без словарных терминов — нормальная ситуация
- Full vocab fallback забивает prompt
- Если слова должны быть, но не найдены → это баг в matching logic (см. Solution #1)

---

## 📊 ТЕСТОВЫЙ СЦЕНАРИЙ

**Словарь:**
```dic
bonded = связанный,, ,
hooder = капюшонник,PERSON,он, инопланетное существо
crushed = раздавил,, ,
```

**Чанк:**
```
The bonded soldier crushed the enemy's weapon. His hooder glowed in the darkness.
```

**Ожидаемый vocabulary для чанка:**
```dic
bonded = связанный
crushed = раздавил
hooder = капюшонник, PERSON, он, инопланетное существо
```

**Текущий результат (BUG):**
```dic
# Пусто или только семантически близкие слова (не exact match)
# Либо fallback на весь словарь (200+ слов)
```

---

## 🔄 ПЛАН ИСПРАВЛЕНИЯ

### Phase 1: Text Search в ner.py (Priority: HIGH)
1. Добавить Stage 1: exact substring match
2. Stage 2: cosine для unmatched с threshold=0.6
3. CPU version: аналогичные изменения
4. Tests: verify exact match работает

### Phase 2: Форматирование (Priority: HIGH)
1. Изменить `_format_standard` без trailing commas
2. Обновить `_format_hunyuan` и `_format_gemma` аналогично
3. Tests: verify output format

### Phase 3: Удалить fallback (Priority: MEDIUM)
1. Удалить fallback на full vocab в `app.py`
2. Tests: verify empty vocab для chunks без terms

---

## 📝 ДОПОЛНИТЕЛЬНЫЕ НАБЛЮДЕНИЯ

### Issue #4: VocabEntry loading без validation

**Файл:** `src/vocabulary_manager.py`, `_load_from_file` (строка 382)

**Код:**
```python
# NO VALIDATION - allow any category and gender values (may be in any language)
```

**Наблюдение:**  
Коммент говорит "no validation", но это правильно — позволяет локализованные категории.

---

### Issue #5: Duplicate handling в load_vocab_from_file

**Файл:** `app.py`, `load_vocab_from_file` (строка 1023)

**Код:**
```python
if key not in vocab:
    vocab[key] = {}  # ❌ Only adds if key not exists
```

**Проблема:**  
Если в .dic файле дубликаты, первый выигрывает. Второй silently игнорируется.

**Решение:**  
Log warning при duplicate entries.

---

### Issue #6: CSV parsing edge cases

**Файл:** `src/vocabulary_manager.py`, `_load_from_file`

**Наблюдение:**  
CSV reader correctly handles quoted fields, но:
```python
csv_reader = csv.reader([rest])
row = next(csv_reader)  # ❌ May fail if rest is empty
```

**Edge case:**  
`term = , category, gender` → target пустой → row[0] = ""

**Код уже проверяет:**
```python
if not source or not target:
    logger.warning(f"Line {line_num}: Empty source or target")
    continue
```

---

## 🎯 RECOMMENDATION

**Immediate fix: Solution #1 (Text Search)**  
Это критический баг — слова из словаря не попадают в чанк.

**Follow-up: Solution #2 (Formatting)**  
Улучшение UX — убрать лишние запятые.

**Optional: Solution #3 (Remove fallback)**  
Cleanup — но зависит от Solution #1 (если matching работает, fallback не нужен).

---

**Next step:**  
Implement Solution #1 в `src/ner.py` — добавить text search stage.