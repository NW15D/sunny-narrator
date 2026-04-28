# JSON Mode — Реализация и конфигурация

**Дата:** 2026-04-28  
**Статус:** ✅ Реализовано  
**Версия:** ccd5ee0

---

## 📋 Конфигурация

### Переменные окружения:

```bash
# .env

# Включить JSON mode для всех этапов перевода (рекомендуется для Qwen, GPT, Hunyuan)
JSON_MODE=true

# Legacy ( игнорируется когда JSON_MODE=true )
DISABLE_JSON_MODE_TRANSLATE=false   # игнорируется при JSON_MODE=true
DISABLE_JSON_MODE_PROOFREAD=false   # игнорируется при JSON_MODE=true
```

### Логика:

| JSON_MODE | Результат |
|-----------|-----------|
| `true` | JSON включён для всех этапов (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT) |
| `false` или не задан | Используется традиционный формат с `<ttext>` тэгами |

---

## 🔄 Этапы перевода в JSON mode

### 1. INITIAL (первичный перевод)

**Input (JSON):**
```json
{
  "source": "Original text",
  "source_lang": "en",
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {"key": "value"},
  "synopsis": "Book synopsis..."
}
```

**Output (JSON):**
```json
{
  "translation": "Переведённый текст"
}
```

---

### 2. REFLECTION (анализ качества)

**Input (JSON):**
```json
{
  "source": "Original text",
  "translation": "Переведённый текст",
  "source_lang": "en",
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {}
}
```

**Output (JSON):**
```json
{
  "suggestions": [
    "Replace 'X' with 'Y' (reason)",
    "Fix grammar: ..."
  ]
}
```

---

### 3. IMPROVE (применение правок)

**Input (JSON):**
```json
{
  "translation": "Переведённый текст",
  "suggestions": ["suggestion 1", "suggestion 2"],
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {}
}
```

**Output (JSON):**
```json
{
  "translation": "Улучшенный перевод"
}
```

---

### 4. FINAL_EDIT (вычитка)

**Input (JSON):**
```json
{
  "translation": "Переведённый текст",
  "target_lang": "ru",
  "country": "RU"
}
```

**Output (JSON):**
```json
{
  "translation": "Финальный перевод"
}
```

---

## 📁 Файлы реализации

### Промпты (src/prompts.json):

```json
{
  "initial_translation_json": {
    "system": "You are a professional literary translator...",
    "user_text": "{json_input}\n\nOutput ONLY valid JSON: {{\"translation\": \"...\"}}"
  },
  "reflection_json": {...},
  "improve_json": {...},
  "editor_json": {...}
}
```

### Конфиг (src/config.py):

```python
# JSON mode control
self.json_mode = os.getenv('JSON_MODE', 'false').lower() in ['true', '1', 't', 'on', 'yes']

# При JSON_MODE=true игнорируем legacy флаги
if self.json_mode:
    self.disable_json_mode_translate = False
    self.disable_json_mode_proofread = False
else:
    self.disable_json_mode_translate = os.getenv('DISABLE_JSON_MODE_TRANSLATE', 'true')...
    self.disable_json_mode_proofread = os.getenv('DISABLE_JSON_MODE_PROOFREAD', 'true')...
```

### Парсинг (src/utils.py):

```python
# JSON input preparation
json_input = json.dumps({
    "source": context.source_text,
    "source_lang": context.source_lang,
    "target_lang": context.target_lang,
    "country": context.country,
    "vocabulary": context.vocab_dict or {},
    "synopsis": context.outline_text or ""
}, ensure_ascii=False)

# Use JSON prompts
prompt_category = "initial_translation_json" if json_mode else "initial_translation"
system_prompt = config.get_prompt(prompt_category, "system")
user_prompt = config.get_prompt(prompt_category, "user_text", json_input=json_input)
```

---

## ⚠️ Поддержка LLM

| Модель | JSON mode | Notes |
|--------|-----------|-------|
| **Qwen** | ✅ Работает | Рекомендуется |
| **GPT-4** | ✅ Работает | |
| **Hunyuan** | ✅ Работает | |
| **Gemma 2/3** | ⚠️ Ограничено | Может возвращать пустой ответ |
| **Llama 3.x** | ⚠️ Ограничено | Зависит от версии |

---

## 🧪 Тестирование

```bash
# Запуск тестов
cd /home/neo/prj/sunny-narrator
pytest tests/test_json_mode.py -v
```

---

## 📝 Changelog

- **2026-04-28:** Добавлен JSON mode для основного перевода (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT)
- **2026-03-30:** Начальная валидация — JSON mode использовался только для metadata

---

**См. также:**
- [specs/2026-04-28-json-llm-response-design.md](../docs/superpowers/specs/2026-04-28-json-llm-response-design.md)
- [plans/2026-04-28-json-mode-plan.md](../docs/superpowers/plans/2026-04-28-json-mode-plan.md)
