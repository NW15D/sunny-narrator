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
# Если .dic файл не найден
Dictionary not found: books/MyBook.dic
Creating from NER...
```

Система:
1. Запускает NER на всём тексте
2. Извлекает имена собственные (PERSON, LOC, ORG)
3. Предлагает переводы через LLM
4. Сохраняет в `MyBook.dic`

### 2. Ручное редактирование

Пользователь редактирует `.dic` файл:

```bash
# Отредактировать словарь
nano books/MyBook.dic

# Добавить гендер для персонажей
Alice = Алиса | PERSON | she
Bob = Боб | PERSON | he
```

### 3. Использование при переводе

При переводе каждого чанка:

```python
# VocabularyManager автоматически:
# 1. Находит термины в чанке (cosine similarity)
# 2. Форматирует для модели (Hunyuan/Gemma/standard)
# 3. Вставляет в промпт
```

## Форматирование для разных моделей

### Hunyuan (Primary LLM)

```
Alice=Aлиса(PERSON) | Wonderland=Страна Чудес(LOC) | Queen=Королева(TITLE)
```

**Особенности:**
- Разделитель: ` | `
- Категория в скобках: `(PERSON)`
- Без gender (Hunyuan не использует)

### Gemma

```
  Alice → Алиса
  Wonderland → Страна Чудес
  Queen → Королева
```

**Особенности:**
- Стрелка: `→`
- Отступ для читаемости

### Standard (Mistral, Llama, Qwen)

```
Alice = Алиса (PERSON) [she]
Wonderland = Страна Чудес (LOC)
Queen = Королева (TITLE)
```

**Особенности:**
- Равенство: `=`
- Категория в скобках: `(PERSON)`
- Gender в квадратных скобках: `[she]`

## Интеграция с промптами

### initial_translation (Stage 1)

```xml
<context>
<synopsis>Previous context...</synopsis>
<vocabulary>
Alice=Aлиса(PERSON) | Wonderland=Страна Чудес(LOC)
</vocabulary>
</context>

<source lang="english">
Alice went to Wonderland.
</source>

Translate to russian...
```

### improve (Stage 3)

```xml
<vocabulary>
Alice=Aлиса(PERSON) | Wonderland=Страна Чудес(LOC)
</vocabulary>

Apply vocabulary terms correctly.
```

### editor (Stage 4 - FINAL_EDIT)

```xml
<vocabulary>
Alice=Aлиса(PERSON) | Wonderland=Страна Чудес(LOC)
</vocabulary>

Проверь соответствие терминов словарю (используй строго).
```

## API VocabularyManager

### Основные методы

```python
from src.vocabulary_manager import VocabularyManager

# Инициализация
manager = VocabularyManager(book_path="books/MyBook.fb2")
vocab = manager.initialize()

# Получить словарь для чанка
entries = manager.get_vocab_for_chunk(chunk_text, s_idx=0, c_idx=0)

# Форматировать для модели
formatted = manager.format_for_model(entries, model="Hunyuan")
# Результат: "Alice=Aлиса(PERSON) | Wonderland=Страна Чудес(LOC)"

# Получить гендер персонажа
gender = manager.get_character_gender("Alice")  # "she"
```

### format_for_model()

Автоматически выбирает формат по названию модели:

| Модель | Формат |
|--------|--------|
| `Hunyuan`, `HY-MT` | `source=target(CAT)` |
| `Gemma` | `  source → target` |
| Остальные | `source = target (CAT) [gender]` |

## Best Practices

### 1. Всегда указывайте gender для PERSON

```dic
# Хорошо
Alice = Алиса | PERSON | she
Bob = Боб | PERSON | he

# Плохо (gender неизвестен)
Alice = Алиса | PERSON
```

### 2. Используйте category для всех терминов

```dic
# Хорошо
Hogwarts = Хогвартс | LOC
Ministry of Magic = Министерство Магии | ORG
Wand = Палочка | ITEM

# Плохо (неясен тип)
Hogwarts = Хогвартс
```

### 3. Добавляйте notes для сложных терминов

```dic
# С комментариями
Sorting Hat = Распределяющая Шляпа | ITEM | | Magical hat that sorts students
The Dark Lord = Тёмный Лорд | TITLE | he | Voldemort's title
```

### 4. Проверяйте consistency

Периодически запускайте проверку:

```bash
# Проверить использование терминов
grep -c "Алиса" translation_output.fb2
grep -c "Элис" translation_output.fb2  # Должно быть 0
```

## Troubleshooting

### Термины не применяются

**Проверьте:**
1. Формат словаря соответствует модели?
2. Термины найдены в чанке (cosine similarity)?
3. Словарь загружен (`vocab_dict` не пуст)?

**Решение:**
```python
# Debug: проверить словарь
print(f"Vocab entries: {len(entries)}")
print(f"Formatted: {formatted}")
```

### Gender не отслеживается

**Проверьте:**
1. Указан ли gender в .dic файле?
2. Категория PERSON или пустая?

**Решение:**
```dic
# Добавить gender
Alice = Алиса | PERSON | she
```

### NER не находит термины

**Проверьте:**
1. Включён ли NER (`NER=true` в .env)?
2. Установлена ли spaCy модель?

**Решение:**
```bash
# Установить модель
python -m spacy download en_core_web_lg
```

## Changelog

- **2026-03-29:** Обновлена документация по форматированию для Hunyuan
- **2026-03-29:** Добавлено описание format_for_model()
- **Previous:** Initial dictionary format documentation
