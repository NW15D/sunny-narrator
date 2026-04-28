# JSON-формат для LLM ответов (Sunny Narrator)

**Goal:** Устранить ошибки извлечения перевода из LLM ответа путём использования JSON-формата вместо XML-тегов.

**Architecture:** Добавить JSON-режим работы с LLM, где вход и выход структурированы в JSON. Это устраняет проблему удаления нужного контекста при очистке от XML-тегов.

---

## Компоненты

### 1. Конфигурация (config.py)
- Добавить `json_mode: bool` флаг
- Переименовать `DISABLE_JSON_MODE_TRANSLATE` → `JSON_MODE` (обратная логика для обратной совместимости)
- По умолчанию `JSON_MODE=false` (текущее поведение)

### 2. Промты (prompts.json)
Новые ключи с суффиксом `_json`:

| Этап | system_json | user_text_json | user_xml_json |
|------|-------------|----------------|---------------|
| initial_translation | JSON-системный | JSON-вход/выход | JSON + XML |
| reflection | JSON-системный | JSON-вход/выход | JSON + XML |
| improve | JSON-системный | JSON-вход/выход | JSON + XML |
| editor (final_edit) | JSON-системный | JSON-вход/выход | JSON + XML |

### 3. Парсинг ответа (utils.py)
Модифицировать `remove_tags_with_check()`:
- Приоритет 1: Извлечь первый валидный JSON блок через regex `re.search(r'(\{.*\})', response, re.DOTALL)`
- Приоритет 2: Парсить JSON `{"translation": "..."}` или `{"suggestions": [...]}`
- Приоритет 3: XML теги `<ttext>...</ttext>`
- Приоритет 4: plain text (fallback)

**Важно:** Использовать "find first valid JSON block" подход для обработки случаев, когда LLM добавляет пояснительный текст вокруг JSON.

### 4. Этапы перевода (utils.py)
Добавить `json_mode=True` в вызовы `llm_service.complete()` для:
- `initial_translation()`
- `reflection()`
- `improve_translation()`
- `final_edit()`

**Обработка ошибок:**
- При пустом `{"suggestions": []}` в REFLECTION — продолжить без предложений (не считать ошибкой)
- При невалидном JSON — retry с текстовым режимом

---

## Data Flow

### INPUT (все этапы)
```json
{
  "source": "текст",
  "target_lang": "russian",
  "country": "Russia",
  "vocabulary": {"термин": "перевод"},
  "synopsis": "краткое содержание"
}
```

### OUTPUT (по этапам)

**INITIAL, IMPROVE, FINAL_EDIT:**
```json
{"translation": "переведенный текст"}
```

**REFLECTION:**
```json
{"suggestions": ["suggestion 1", "suggestion 2"]}
```

---

## Полные входные данные по этапам

### INITIAL_TRANSLATION
```json
{
  "source": "текст для перевода",
  "source_lang": "english",
  "target_lang": "russian",
  "country": "Russia",
  "vocabulary": {"термин": "перевод"},
  "synopsis": "краткое содержание (outline_text)"
}
```

### REFLECTION
```json
{
  "source": "исходный текст",
  "translation": "текущий перевод",
  "source_lang": "english",
  "target_lang": "russian",
  "country": "Russia",
  "vocabulary": {"термин": "перевод"}
}
```

### IMPROVE
```json
{
  "translation": "перевод после reflection",
  "suggestions": ["suggestion 1", "suggestion 2"],
  "target_lang": "russian",
  "country": "Russia",
  "vocabulary": {"термин": "перевод"}
}
```

### FINAL_EDIT
```json
{
  "translation": "перевод после improve",
  "target_lang": "russian",
  "country": "Russia"
}
```

---

## Testing Strategy

1. **Unit tests:** Тестирование парсинга JSON-ответов
2. **Integration tests:** Тестирование полного цикла перевода с JSON_MODE=true
3. **Fallback tests:** Проверка переключения на текстовый режим при ошибках JSON
4. **Comparison tests:** Сравнение результатов с текущим XML-режимом

---

## Конфигурация

**.env:**
```
JSON_MODE=true
```

**config.py:**
```python
self.json_mode = os.getenv('JSON_MODE', 'false').lower() in ['true', '1', 't', 'on', 'yes']
```
