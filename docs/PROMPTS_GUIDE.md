# Prompts Guide — Sunny Narrator

## 📋 Структура промптов

Все промпты хранятся в `src/prompts.json` и разделены по категориям:

### Primary LLM (Translation)
- `initial_translation` — Первичный перевод текста
- `synopsis` — Создание синопсиса для контекста

### Secondary LLM (Quality/Editing)
- `reflection` — Анализ качества перевода
- `improve` — Применение замечаний
- `editor` — Финальная вычитка (Stage 5)

### Utilities
- `vocabulary` — Генерация словаря терминов
- `metadata_translation` — Перевод метаданных
- `image_generation` — Генерация обложек

---

## 🔧 Режим sys_not_promt (System Prompt Merging)

### Проблема

Некоторые LLM модели **не поддерживают** отдельный системный промпт (role: "system"):

| Модель | Системный промпт | Примечания |
|--------|------------------|------------|
| **Gemma 2** | ❌ НЕ поддерживает | Требует объединения с user prompt |
| **Gemma 3** | ❌ НЕ поддерживает | Требует объединения с user prompt |
| **Mistral 7B** | ✅ Поддерживает | Стандартный режим |
| **Mistral Large** | ✅ Поддерживает | Стандартный режим |
| **Llama 3.2** | ✅ Поддерживает | Стандартный режим |
| **Llama 3.3** | ✅ Поддерживает | Стандартный режим |
| **Hunyuan** | ✅ Поддерживает | Стандартный режим |
| **Qwen** | ✅ Поддерживает | Стандартный режим |

### Решение

Для моделей без поддержки системного промпта используется режим `sys_not_promt`:
- Системный промпт **объединяется** с пользовательским
- Формат: `"{system_prompt}\n\n{user_prompt}"`
- Отправляется как одно сообщение с role: "user"

### Настройка

В `.env` файле укажите флаги для Primary и Secondary LLM:

```bash
# Primary LLM (Translation)
MODEL_TRANSLATE=google/gemma-2-27b-it
S_PROMT_TRANSLATE=true    # true = объединять system+user

# Secondary LLM (Proofreading)
MODEL_PROOFREAD=Mistral
S_PROMT_PROOFREAD=false   # false = раздельные сообщения
```

### Переменные окружения

| Переменная | Описание | Значения |
|------------|----------|----------|
| `S_PROMT_TRANSLATE` | Режим для Primary LLM | `true` / `false` |
| `S_PROMT_PROOFREAD` | Режим для Secondary LLM | `true` / `false` |
| `S_PROMT_IMAGES` | Режим для Image Generation | `true` / `false` |

---

## 📊 Рекомендации по моделям

### Primary LLM (Translation)

| Модель | S_PROMT_TRANSLATE | Примечания |
|--------|-------------------|------------|
| `google/gemma-2-9b-it` | **true** | Gemma 2 не поддерживает system |
| `google/gemma-2-27b-it` | **true** | Gemma 2 не поддерживает system |
| `google/gemma-3-12b-it` | **true** | Gemma 3 не поддерживает system |
| `mistralai/Mistral-7B` | false | Поддерживает system |
| `mistralai/Mistral-Large` | false | Поддерживает system |
| `meta-llama/Llama-3.2` | false | Поддерживает system |
| `meta-llama/Llama-3.3` | false | Поддерживает system |
| `tencent/Hunyuan` | false | Поддерживает system |
| `Qwen/Qwen-2.5` | false | Поддерживает system |

### Secondary LLM (Proofreading/Editing)

| Модель | S_PROMT_PROOFREAD | Примечания |
|--------|-------------------|------------|
| `google/gemma-2-9b-it` | **true** | Gemma 2 не поддерживает system |
| `Mistral-7B-Instruct` | false | Поддерживает system |
| `Ministral-8B` | false | Поддерживает system |
| `Qwen-2.5-7B` | false | Поддерживает system |

---

## 🎯 Структура prompts.json

### Пример для Primary LLM (Hunyuan)

```json
{
    "initial_translation": {
        "system": "You are a professional literary translator...",
        "user_xml": "<context>...</context>...",
        "user_text": "...",
        "user_hunyuan": "{outline_text}\n\n参考上面的信息..."
    },
    "synopsis": {
        "system": "You are an expert summarizer...",
        "user": "<text>...</text>...",
        "user_hunyuan": "<text>...</text>\n\n请用{target_lang}..."
    }
}
```

### Пример для Secondary LLM

```json
{
    "reflection": {
        "system": "You are a literary translation quality reviewer...",
        "user_xml": "<task>Target language: {target_lang}...</task>...",
        "user_text": "..."
    },
    "improve": {
        "system": "You are a literary translation editor...",
        "user_xml": "<task>Target language: {target_lang}...</task>...",
        "user_text": "..."
    },
    "editor": {
        "system": "Ты профессиональный редактор-переводчик...",
        "user_xml": "<original>...</original>...",
        "user_text": "...",
        "user_hunyuan": "..."
    }
}
```

---

## 🔄 Workflow (5 этапов)

```
┌─────────────────────────────────────────────────────────────────┐
│ ЭТАП 1: INITIAL (Primary LLM)                                   │
│ Промпт: initial_translation (system + user_hunyuan/user_xml)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ ЭТАП 2: REFLECTION (Secondary LLM)                              │
│ Промпт: reflection (system + user_xml/user_text)                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ ЭТАП 3: IMPROVE (Secondary LLM)                                 │
│ Промпт: improve (system + user_xml/user_text)                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ ЭТАП 4: FINAL_EDIT (Secondary LLM) 🆕                            │
│ Промпт: editor (system + user_xml/user_text/user_hunyuan)       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ ЭТАП 5: SYNOPSIS (Primary LLM) ← из финального перевода         │
│ Промпт: synopsis (system + user/user_hunyuan)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Конфигурация

### .env файл

```bash
# Primary LLM
MODEL_TRANSLATE=google/gemma-2-27b-it
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
S_PROMT_TRANSLATE=true          # ⚠️ true для Gemma!
TEMP_TRANSLATE=0.01

# Secondary LLM
MODEL_PROOFREAD=Mistral
API_BASE_PROOFREAD=http://localhost:11434/v1
API_KEY_PROOFREAD=your-key
S_PROMT_PROOFREAD=false         # false для Mistral
TEMP_PROOFREAD=0.7

# Общие
SOURCE_LANG=english
TARGET_LANG=russian
COUNTRY=Россия
```

---

## 🧪 Тестирование

Проверка режима sys_not_promt:

```python
from src.config import Config
from src.utils import llm_service, LLMRole

config = Config()

print(f"Primary sys_not_promt: {config.sys_not_promt_translate}")
print(f"Secondary sys_not_promt: {config.sys_not_promt_proofread}")

# Тестовый вызов
result = llm_service.complete(
    role=LLMRole.PRIMARY,
    system_prompt="You are a translator",
    user_prompt="Translate: Hello",
    max_tokens=100
)
```

---

## 📝 Changelog

- **2026-03-29**: Добавлен режим sys_not_promt для Gemma 2/3
- **2026-03-29**: Разделение промптов на Primary/Secondary LLM
- **2026-03-29**: Добавлен Stage 5 (FINAL_EDIT) с промптом editor

---

## 📦 JSON Mode

Set `JSON_MODE=true` in `.env` to use structured JSON for LLM input/output.

### Benefits
- More reliable parsing (no XML tag conflicts)
- Structured input with vocabulary, synopsis, context
- Consistent output format across all stages

### Configuration
```bash
# .env
JSON_MODE=true
```

### Input Format (all stages)
```json
{
  "source": "текст для перевода",
  "source_lang": "english",
  "target_lang": "russian",
  "country": "Russia",
  "vocabulary": {"термин": "перевод"},
  "synopsis": "краткое содержание"
}
```

### Output Format (by stage)

**INITIAL, IMPROVE, FINAL_EDIT:**
```json
{"translation": "переведенный текст"}
```

**REFLECTION:**
```json
{"suggestions": ["suggestion 1", "suggestion 2"]}
```

### Prompts
JSON prompts are defined in `prompts.json` with `_json` suffix:
- `initial_translation_json`
- `reflection_json`
- `improve_json`
- `editor_json`

### Fallback
If JSON parsing fails, the system falls back to XML tag extraction.

- **2026-04-28**: Added JSON Mode for structured LLM input/output
