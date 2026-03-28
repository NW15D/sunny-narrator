# План рефакторинга фичи NER словаря

## Текущее состояние (проблемы)

### 1. Разрозненная логика
- Создание словаря в `app.py` (main())
- NER в `src/ner.py`
- Перевод терминов в `src/utils.py::vocabulary()`
- Использование в `TranslationEngine.load_vocab_for_chunk()`
- Нет единого менеджера

### 2. Нет модель-специфичного форматирования
- Все модели получают словарь в одном формате
- Hunyuan поддерживает terminology intervention — не используется
- Нет оптимизации под конкретные модели

### 3. Ограниченная структура данных
- Только `source = target`
- Нет поля для gender персонажей
- Нет категорий (PERSON, ORG, LOC)
- Нет notes для пользователя
- Нет отслеживания книги в серии

### 4. Проблемы с matching
- Cosine similarity matching работает, но:
  - Нет кеширования результатов
  - Нет отслеживания где (в каких чанках) встречается термин
  - Нет приоритизации часто используемых терминов

### 5. Нет интеграции с синопсисом
- Gender персонажей не передаётся в синопсис
- Нет единого Character tracking между словарём и синопсисом

---

## Целевая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOCABULARY MANAGER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│  │  Initialize │────▶│    Load     │────▶│   Match     │      │
│  │   (NER)     │     │  from .dic  │     │  per chunk  │      │
│  └─────────────┘     └─────────────┘     └──────┬──────┘      │
│                                                 │               │
│                                                 ▼               │
│                                        ┌─────────────┐         │
│                                        │   Format    │         │
│                                        │  for model  │         │
│                                        │ (Hunyuan/   │         │
│                                        │  Gemma/etc) │         │
│                                        └─────────────┘         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Character Tracker                    │   │
│  │  - Names + gender + aliases                            │   │
│  │  - Mention tracking per chunk                          │   │
│  │  - Integration with SynopsisManager                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Series Support                       │   │
│  │  - Load vocab from previous books                      │   │
│  │  - Consistent translation across series                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Новый формат .dic файла

```
# Vocabulary for BookName
# Format: source = target | category | gender | notes

# Characters
Alice = Алиса | PERSON | she | Main character, curious girl
Mad Hatter = Шляпный Болван | PERSON | he | Eccentric tea party host
Cheshire Cat = Чеширский Кот | PERSON | it | Mysterious, grinning cat

# Locations  
Wonderland = Страна Чудес | LOC | | Magical world setting
Rabbit Hole = Кроличья Нора | LOC | | Entrance to Wonderland

# Organizations
Queen's Court = Двор Королевы | ORG | | Where trials happen

# Other terms
Drink Me = Выпей меня | ITEM | | Potion label
Eat Me = Съешь меня | ITEM | | Cake label
```

---

## План реализации

### Этап 1: Создать VocabularyManager ✅

**Файл:** `src/vocabulary_manager.py`

**Классы:**
- `VocabEntry` — запись словаря с полями: source, target, category, gender, notes, book_origin
- `Character` — персонаж: name, gender, aliases, mentions
- `VocabularyManager` — основной менеджер

**API:**
```python
manager = VocabularyManager(book_path="books/Alice.fb2")

# Initialize (creates or loads .dic)
vocab = manager.initialize()  # exits if new dict created

# Get terms for chunk
entries = manager.get_vocab_for_chunk(chunk_text, s_idx, c_idx)

# Format for specific model
hunyuan_vocab = manager.format_for_model(entries, model="Hunyuan")
standard_vocab = manager.format_for_model(entries, model="Mistral")

# Character operations
gender = manager.get_character_gender("Alice")
manager.update_character_mentions("Alice", chunk_idx=5)

# Series support
series_vocab = manager.get_series_vocab(["book1.dic", "book2.dic"])
```

### Этап 2: Модель-специфичное форматирование

**Hunyuan MT:**
```python
def _format_hunyuan(self, entries):
    # Format: "Source=Target(CATEGORY) | Source2=Target2 | ..."
    # Supports terminology intervention
    return " | ".join(f"{e.source}={e.target}({e.category})" 
                      for e in entries)
```

**Gemma/TranslateGemma:**
```python
def _format_gemma(self, entries):
    # Structured list with arrows
    return "\n".join(f"  {e.source} → {e.target}" for e in entries)
```

**Standard:**
```python
def _format_standard(self, entries):
    # Full format with gender and notes
    return "\n".join(f"{e.source} = {e.target} ({e.category}) [{e.gender}]"
                     for e in entries)
```

### Этап 3: Интеграция в TranslationEngine

**В `app.py`:**

```python
class TranslationEngine:
    def __init__(self, output_tfile, book_path):
        # ... existing ...
        
        # NEW: Vocabulary manager
        from src.vocabulary_manager import get_vocabulary_manager
        self.vocab_manager = get_vocabulary_manager(book_path)
        self.vocab = self.vocab_manager.initialize()
    
    def load_vocab_for_chunk(self, chunk, s_idx, c_idx):
        # NEW: Use VocabularyManager
        entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
        
        # Format for current model
        model = config.model_translate
        formatted = self.vocab_manager.format_for_model(entries, model)
        
        return formatted
    
    def process_all_chunks(self, ...):
        for item in all_chunks:
            # ...
            
            # Get formatted vocab for this chunk
            vocab_for_chunk = self.load_vocab_for_chunk(chunk, s_idx, c_idx)
            
            # Pass to translation
            final_content, _ = self.process_chunk_recursive(
                chunk, s_idx, c_idx, g_id, 
                vocab_dict_key, current_context,
                vocab_list=vocab_for_chunk  # NEW: formatted vocab
            )
            
            # Update character mentions
            self._update_character_tracking(final_content, s_idx, c_idx)
```

### Этап 4: Интеграция с SynopsisManager

**Character tracking в синопсис:**

```python
class SynopsisManager:
    def generate_synopsis_with_characters(self, text, vocab_manager):
        # Extract characters mentioned in this chunk
        characters = []
        for name, char in vocab_manager.characters.items():
            if name.lower() in text.lower():
                characters.append(f"{char.name} ({char.gender})")
        
        synopsis = self._generate_synopsis(text)
        
        # Add character context
        if characters:
            char_context = "Characters: " + ", ".join(characters)
            synopsis = char_context + ". " + synopsis
        
        return synopsis
```

### Этап 5: Series Support

**Загрузка словарей предыдущих книг:**

```python
# In main():
if config.series_mode:
    # Find previous books in series
    series_files = find_series_books(config.myfile)
    series_vocab = vocab_manager.get_series_vocab(series_files)
    
    # Merge with current book's vocab
    for key, entry in series_vocab.items():
        if key not in vocab_manager.vocab:
            vocab_manager.vocab[key] = entry
```

---

## Улучшения (предложения)

### 1. Smart Term Matching

```python
def get_vocab_for_chunk(self, chunk_text, s_idx, c_idx, 
                        max_terms=20, min_confidence=0.8):
    """
    Get most relevant vocabulary for chunk.
    
    - Limit number of terms (avoid prompt overflow)
    - Prioritize by:
      1. Frequency in book (how often term appears)
      2. Recency (terms from recent chunks)
      3. Confidence score from cosine similarity
    """
    all_matches = self._find_all_matches(chunk_text)
    
    # Score and rank
    scored = []
    for match in all_matches:
        score = (
            match.confidence * 0.5 +
            match.frequency_in_book * 0.3 +
            match.recency_score * 0.2
        )
        scored.append((match, score))
    
    # Return top N
    scored.sort(key=lambda x: x[1], reverse=True)
    return [m for m, s in scored[:max_terms]]
```

### 2. Gender Inference

```python
def infer_gender(self, name, text_context):
    """
    Infer character gender from text context.
    
    Look for pronouns near character mentions:
    - "Alice said she would..." → she
    - "Bob raised his hand..." → he
    """
    # Find sentences with character name
    sentences = extract_sentences_with_name(text_context, name)
    
    # Count pronouns
    pronouns = {"he": 0, "she": 0, "it": 0, "they": 0}
    for sent in sentences:
        for pronoun in pronouns:
            if pronoun in sent.lower():
                pronouns[pronoun] += 1
    
    # Return most frequent
    return max(pronouns, key=pronouns.get)
```

### 3. Auto-Update Dictionary

```python
def suggest_dictionary_updates(self, translated_chunks):
    """
    Suggest new entries or corrections based on translation.
    
    - Detect inconsistent translations
    - Find new named entities not in dictionary
    - Suggest gender corrections
    """
    inconsistencies = self._find_inconsistencies(translated_chunks)
    new_entities = self._find_new_entities(translated_chunks)
    
    return {
        "inconsistencies": inconsistencies,
        "new_entities": new_entities,
        "suggested_updates": self._generate_suggestions(inconsistencies)
    }
```

### 4. Vocabulary Validation

```python
def validate_dictionary(self):
    """
    Check dictionary for common issues.
    
    - Duplicate entries
    - Inconsistent gender for same character
    - Missing translations
    - Orphaned entries (not in book)
    """
    issues = []
    
    # Check for duplicates
    seen = {}
    for key, entry in self.vocab.items():
        if entry.source in seen:
            issues.append(f"Duplicate: {entry.source}")
        seen[entry.source] = key
    
    # Check for inconsistent gender
    for char in self.characters.values():
        gender_mentions = char.mentions_with_gender
        if len(set(gender_mentions)) > 1:
            issues.append(f"Inconsistent gender for {char.name}")
    
    return issues
```

---

## Timeline

| Этап | Время | Статус |
|------|-------|--------|
| 1. VocabularyManager | 3ч | ✅ Готово |
| 2. Model-specific formatting | 1ч | ✅ Готово |
| 3. Integration в app.py | 2ч | 🔄 Следующий |
| 4. SynopsisManager integration | 1ч | ⏳ |
| 5. Series support | 2ч | ⏳ |
| 6. Тестирование | 2ч | ⏳ |

**Итого:** ~11 часов

---

## Миграция

### Обратная совместимость

Старые .dic файлы в формате `source = target` продолжат работать:

```python
def _parse_line(self, line):
    if '|' in line:
        # New format: source = target | category | gender | notes
        return self._parse_extended(line)
    else:
        # Legacy format: source = target
        return self._parse_legacy(line)
```

### Флаг для включения

```python
config.use_vocabulary_manager = True  # новое поведение
config.use_vocabulary_manager = False  # legacy
```