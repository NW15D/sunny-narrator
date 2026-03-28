# Формат словаря (.dic файл)

## Обзор

Словарь (`*.dic`) — это файл с терминами для обеспечения консистентности перевода. Он содержит:
- Переводы имен персонажей
- Географические названия
- Специфическую терминологию
- Gender информацию для корректного использования местоимений

## Формат файла

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

## Структура записи

| Поле | Обязательное | Описание | Пример |
|------|---------------|----------|--------|
| **source** | ✅ | Термин в исходном языке | `Alice` |
| **target** | ✅ | Перевод термина | `Алиса` |
| **category** | ⚪ | Тип сущности | `PERSON`, `LOC`, `ORG`, `ITEM` |
| **gender** | ⚪ | Гендер для персонажей | `he`, `she`, `it`, `they` |
| **notes** | ⚪ | Комментарии пользователя | `Main character` |

### Разделитель

Используйте `|` для разделения полей после перевода:

```
source = target | category | gender | notes
```

### Legacy формат

Старый формат без расширенных полей также поддерживается:

```
Alice = Алиса
Wonderland = Страна Чудес
```

## Категории (category)

| Категория | Описание | Примеры |
|-----------|----------|---------|
| **PERSON** | Люди, персонажи | `Alice = Алиса | PERSON | she` |
| **LOC** | Локации, места | `Wonderland = Страна Чудес | LOC` |
| **ORG** | Организации, группы | `Queen's Court = Двор Королевы | ORG` |
| **ITEM** | Объекты, артефакты | `Magic Sword = Магический Меч | ITEM` |
| **TERM** | Специфические термины | `Portals = Порталы | TERM` |
| **TITLE** | Заголовки, титулы | `Queen = Королева | TITLE` |

Если category не указана, по умолчанию считается `PERSON` для_gender tracking.

## Gender (гендер)

Gender используется для:
1. Корректных местоимений в переводе (he/she/it → он/она/оно)
2. Character tracking в SynopsisManager
3. Consistency across chunks

### Значения gender

| Значение | Описание | Местоимения |
|----------|----------|-------------|
| `he` | Мужской | он, его, ему |
| `she` | Женский | она, её, ей |
| `it` | Неодушевлённое | оно, его |
| `they` | Множественное/неопределённое | они, их |

### Как определить gender

1. **Из текста**: LLM может推断 gender по местоимениям рядом с именем
2. **Из словаря**: Пользователь указывает вручную в .dic файле
3. **По умолчанию**: PERSON без gender → не отслеживается

## Workflow работы со словарём

### 1. Автоматическое создание

При первом запуске перевода:

```bash
python app.py --file books/MyBook.fb2
```

Если `.dic` файл не найден:
1. NER извлекает entities из книги
2. LLM переводит их
3. Создается `books/MyBook.dic`
4. Программа завершается с сообщением

```
Dictionary created: books/MyBook.dic
Please review and edit the dictionary, then restart.
```

### 2. Ручное редактирование

Отредактируйте `.dic` файл:

```bash
nano books/MyBook.dic
# или
vim books/MyBook.dic
```

Добавьте:
- Gender для персонажей (`he`, `she`, `it`)
- Notes для контекста
- Missing terms (если NER пропустил)

### 3. Запуск перевода

```bash
python app.py --file books/MyBook.fb2
```

Теперь словарь загружается и используется для каждого чанка.

## Matching терминов

### Cosine Similarity

VocabularyManager использует NER с cosine similarity для поиска терминов в чанке:

1. Векторизация термина и текста чанка
2. Cosine similarity matching
3. Threshold для отбора

### Кеширование

Результаты matching кешируются:

```
matched_terms_cache: Dict[(section_idx, chunk_idx)] = List[term_keys]
```

При retry того же чанка — cache используется.

## Модель-специфичное форматирование

Different LLM models получают словарь в разных форматах:

### Hunyuan MT

```
Alice=Алиса(PERSON) | Mad Hatter=Шляпный Болван(PERSON) | Wonderland=Страна Чудес(LOC)
```

Особенность: Hunyuan поддерживает terminology intervention — словарь интегрируется в generation process.

### Gemma / TranslateGemma

```
Alice → Алиса
Mad Hatter → Шляпный Болван
Wonderland → Страна Чудес
```

Структурированный список с стрелками.

### Standard (Mistral, Qwen, etc.)

```
Alice = Алиса (PERSON) [she]
Mad Hatter = Шляпный Болван (PERSON) [he]
Wonderland = Страна Чудес (LOC)
```

Полный формат с category и gender.

## Series Support (мультикнижные серии)

### Загрузка словарей предыдущих книг

Для серии книг можно объединить словари:

```python
# В config.py или при запуске
series_books = [
    "books/Book1.dic",
    "books/Book2.dic",
    "books/Book3.dic"
]

series_vocab = vocab_manager.get_series_vocab(series_books)
```

### book_origin поле

При загрузке series vocab, каждое entry получает `book_origin`:

```
Alice = Алиса | PERSON | she | Main character | Book1
```

### Консистентность в серии

- Персонажи переводятся одинаково во всех книгах
- Gender сохраняется
- Новые термины добавляются в текущий словарь

## Character Registry Integration

### Flow gender информации

```
.dic файл
    ↓
VocabularyManager._extract_characters()
    ↓
CharacterRegistry.add_character(gender=...)
    ↓
SynopsisManager.get_character_context_line()
    ↓
"Characters: Alice (she), Bob (he)"
    ↓
Prompt для следующего чанка
```

### Character tracking

CharacterRegistry отслеживает:

1. **Mentions**: В каких (section, chunk) упоминается персонаж
2. **Aliases**: Все формы имени (source + target + alternatives)
3. **Gender**: Из словаря или inferred из текста

### Synopsis integration

SynopsisManager включает персонажей:

```
Синопсис: Alice (she) и Bob (he) идут в парк. Солнце светит...
```

Это помогает LLM:
- Использовать правильные местоимения
- Сохранять консистентность имен
- Отслеживать персонажей через chunks

## Пример полного словаря

```
# Vocabulary for Alice_in_Wonderland
# Format: source = target | category | gender | notes
# Generated: 2026-03-28

# ============================================
# MAIN CHARACTERS
# ============================================
Alice = Алиса | PERSON | she | Main protagonist, curious girl
White Rabbit = Белый Кролик | PERSON | he | Anxious, always late
Mad Hatter = Шляпный Болван | PERSON | he | Eccentric tea party host
Cheshire Cat = Чеширский Кот | PERSON | it | Grinning, disappears
Queen of Hearts = Королева Червей | PERSON | she | Villain, angry
King of Hearts = Король Червей | PERSON | he | Mild, fearful
March Hare = Мартовский Заяц | PERSON | he | Mad tea party guest
Dormouse = Соня | PERSON | it | Sleepy tea party guest

# ============================================
# LOCATIONS
# ============================================
Wonderland = Страна Чудес | LOC | | Magical world
Rabbit Hole = Кроличья Нора | LOC | | Entrance to Wonderland
Tea Party Garden = Сад Чаепития | LOC | | Where Hatter hosts
Queen's Court = Двор Королевы | LOC | | Trial location
Croquet Ground = Крокетное Поле | LOC | | Queen's game

# ============================================
# ITEMS
# ============================================
Drink Me = Выпей меня | ITEM | | Potion bottle label
Eat Me = Съешь меня | ITEM | | Cake label
Golden Key = Золотой Ключ | ITEM | | Opens tiny door
Looking Glass = Зеркало | ITEM | | Portal (in sequel)

# ============================================
# TERMS
# ============================================
Curiouser = Любопытнее | TERM | | Alice's word
Off with her head! = Отрубить ей голову! | TERM | | Queen's phrase
```

## Troubleshooting

### Проблема: Термин не используется

**Решение:**
1. Проверьте exact spelling в .dic и тексте
2. Case-insensitive matching — но лучше совпадать
3. Убедитесь что NER включен (`ner_opt: true`)

### Проблема: Неконсистентный перевод имени

**Решение:**
1. Добавьте в словарь с правильным переводом
2. Укажите category=PERSON для character tracking
3. Перезапустите перевод

### Проблема: Неверный gender

**Решение:**
1. Проверьте gender поле в .dic
2. Если LLM inferred wrong → исправьте вручную
3. Gender из словаря — source of truth

### Проблема: Словарь не создается

**Решение:**
1. Проверьте `ner_opt` в config
2. Убедитесь что book parsed correctly
3. Проверьте logs для NER errors

## Config параметры

| Параметр | Описание | Default |
|----------|----------|---------|
| `ner_opt` | Включить NER для словаря | `true` |
| `source_lang` | Исходный язык | `english` |
| `target_lang` | Целевой язык | `russian` |
| `model_translate` | Модель для перевода | `Hunyuan` |

## API Usage

### VocabularyManager

```python
from src.vocabulary_manager import VocabularyManager, get_vocabulary_manager

# Initialize
manager = get_vocabulary_manager("books/MyBook.fb2")
vocab = manager.initialize()  # Load or create

# Get terms for chunk
entries = manager.get_vocab_for_chunk(chunk_text, section_idx, chunk_idx)

# Format for model
formatted = manager.format_for_model(entries, model="Hunyuan")

# Character gender
gender = manager.get_character_gender("Alice")

# Series support
series_vocab = manager.get_series_vocab(["book1.dic", "book2.dic"])
```

### Character Registry

```python
from src.character_registry import get_character_registry

registry = get_character_registry()

# Detect mentions
mentioned = registry.detect_mentions(text, section_idx, chunk_idx)

# Get for synopsis
chars = registry.get_characters_for_synopsis(section_idx, chunk_idx)
context_line = registry.get_character_context_line(section_idx, chunk_idx)

# Stats
stats = registry.get_stats()
```

---

**Связанные документы:**
- [SYNOPSIS_REFACTOR_PLAN.md](./SYNOPSIS_REFACTOR_PLAN.md) — SynopsisManager architecture
- [VOCABULARY_REFACTOR_PLAN.md](./VOCABULARY_REFACTOR_PLAN.md) — VocabularyManager architecture