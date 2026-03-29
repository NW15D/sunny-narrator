# План рефакторинга фичи синопсиса

## Текущее состояние (проблемы)

### 1. Неправильная логика генерации
- Синопсис генерируется на **каждом** чанке, включая первый
- Нет проверки "первый чанк секции = пустой синопсис"
- Синопсис перезаписывается вместо накопления

### 2. Отсутствие разделения по секциям
- `shared_outline` глобальный для всей книги
- Синопсис перетекает между секциями (не сбрасывается)
- Нет изоляции контекста между разными section

### 3. Неправильное использование
- Синопсис передаётся в `outline_text` как строка
- Нет типизации, нет валидации
- Нет логирования что было передано

---

## Целевая архитектура

### Правила работы синопсиса

```
┌─────────────────────────────────────────────────────────────┐
│                      ПРАВИЛА СИНОПСИСА                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Секция 1                    Секция 2                       │
│  ┌────────┐                  ┌────────┐                    │
│  │Чанк 1  │  synopsis=""     │Чанк 1  │  synopsis=""       │
│  │        │  (пустой)        │        │  (пустой)          │
│  └────┬───┘                  └────┬───┘                    │
│       │                           │                        │
│       ▼                           ▼                        │
│  ┌────────┐                  ┌────────┐                    │
│  │Чанк 2  │  synopsis=       │Чанк 2  │  synopsis=         │
│  │        │  "из чанка 1"    │        │  "из чанка 1"      │
│  └────┬───┘                  └────┬───┘                    │
│       │                           │                        │
│       ▼                           ▼                        │
│  ┌────────┐                  ┌────────┐                    │
│  │Чанк 3  │  synopsis=       │Чанк 3  │  synopsis=         │
│  │        │  "из 1+2"        │        │  "из 1+2"          │
│  └────────┘                  └────────┘                    │
│                                                             │
│  ПРАВИЛО 1: Первый чанк секции → synopsis = ""              │
│  ПРАВИЛО 2: Синопсис = краткое содержание ПРЕДЫДУЩИХ чанков │
│  ПРАВИЛО 3: Синопсис сбрасывается при смене секции          │
│  ПРАВИЛО 4: Синопсис накапливается (не перезаписывается)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Что должен содержать синопсис

1. **Имена персонажей + gender**
   - "Alice (she), Bob (he), the cat (it)"
   
2. **Ключевая терминология**
   - Специфические термины из словаря
   - Собственные имена
   
3. **Контекст ситуации**
   - Где происходит действие
   - Текущая сцена

---

## План реализации

### Этап 1: Создать `SynopsisManager` ✅

**Файл:** `src/synopsis_manager.py`

**Классы:**
- `SectionContext` — контекст одной секции
- `SynopsisManager` — управление синопсисами всех секций
- `SynopsisGenerator` — LLM-генерация синопсиса

**API:**
```python
manager = SynopsisManager()

# Получить синопсис для чанка
synopsis = manager.get_synopsis(section_idx=0, chunk_idx=2)
# Returns: "" для chunk_idx=0, accumulated для chunk_idx>0

# Сохранить результат чанка
manager.add_chunk_result(section_idx, chunk_idx, final_translation)
```

### Этап 2: Обновить `TranslationEngine`

**В `app.py`:**

```python
class TranslationEngine:
    def __init__(self, output_tfile):
        # ... existing code ...
        self.synopsis_manager = SynopsisManager()
    
    def process_chunk_recursive(self, chunk, s_idx, c_idx, ...):
        # Get synopsis for this chunk
        current_synopsis = self.synopsis_manager.get_synopsis(s_idx, c_idx)
        
        # Translate with synopsis
        final_content, _ = self.translate_chunk_wrapper(
            ..., outline_text=current_synopsis, ...
        )
        
        # Save result for future chunks
        self.synopsis_manager.add_chunk_result(s_idx, c_idx, final_content)
        
        return final_content, ""
```

### Этап 3: Улучшить генерацию синопсиса

**Текущая проблема:**
- Синопсис генерируется отдельным вызовом LLM
- Это дорого и медленно

**Решение:**
- Генерировать синопсис как побочный продукт перевода
- Добавить в pipeline: "перевод + синопсис" одним вызовом

**Новый промпт:**
```json
{
  "initial_translation": {
    "system": "You are a professional literary translator...",
    "user": "...",
    "output_format": "Return JSON with 'translation' and 'synopsis' fields"
  }
}
```

### Этап 4: Оптимизации

1. **Lazy synopsis generation**
   - Не генерировать синопсис для последнего чанка секции
   - Ограничить длину синопсиса (max 500 chars)
   - Хранить только последние 3 чанка в контексте

2. **Caching**
   - Кешировать синопсисы на диск
   - При retry не перегенерировать

3. **Smart truncation**
   - При превышении лимита токенов — суммаризировать старые чанки
   - Сохранять только ключевую информацию

---

## Улучшения (предложения)

### 1. Character Tracking

```python
@dataclass
class Character:
    name: str
    gender: str  # "he", "she", "it"
    first_mention_chunk: int
    mentions: List[str]  # контексты упоминаний

class SynopsisManager:
    def extract_characters(self, text: str) -> List[Character]:
        # Использовать NER для извлечения имён
        # Определять gender по местоимениям в тексте
        pass
```

### 2. Terminology Consistency

```python
class SynopsisManager:
    def track_terminology(self, vocab_dict: Dict, used_terms: List[str]):
        # Отслеживать какие термины из словаря уже использовались
        # Включать их в синопсис для консистентности
        pass
```

### 3. Section-Aware Summaries

```python
class SynopsisManager:
    def generate_section_summary(self, section_idx: int) -> str:
        # По окончании секции — генерировать summary всей секции
        # Использовать как "pre-context" для следующей секции
        pass
```

---

## Миграция

### Обратная совместимость

```python
# Старый код (работает)
translate(..., outline_text="some text", ...)

# Новый код (рекомендуется)
manager = SynopsisManager()
synopsis = manager.get_synopsis(section_idx, chunk_idx)
translate(..., outline_text=synopsis, ...)
manager.add_chunk_result(section_idx, chunk_idx, result)
```

### Флаг для включения

```python
config.use_synopsis_manager = True  # новое поведение
config.use_synopsis_manager = False  # legacy (текущее)
```

---

## Тестирование

### Unit tests
```python
def test_first_chunk_empty_synopsis():
    manager = SynopsisManager()
    assert manager.get_synopsis(0, 0) == ""

def test_second_chunk_has_synopsis():
    manager = SynopsisManager()
    manager.add_chunk_result(0, 0, "Alice went to the park...")
    synopsis = manager.get_synopsis(0, 1)
    assert "Alice" in synopsis

def test_section_isolation():
    manager = SynopsisManager()
    manager.add_chunk_result(0, 0, "Section 1 content...")
    # New section should have empty synopsis
    assert manager.get_synopsis(1, 0) == ""
```

### Integration tests
- Перевод книги с проверкой консистентности имён
- Проверка gender consistency через несколько чанков

---

## Timeline

| Этап | Время | Статус |
|------|-------|--------|
| 1. SynopsisManager | 2ч | ✅ Готово |
| 2. Integration в app.py | 2ч | 🔄 Следующий |
| 3. Улучшенная генерация | 3ч | ⏳ |
| 4. Оптимизации | 2ч | ⏳ |
| 5. Тестирование | 2ч | ⏳ |

**Итого:** ~11 часов
