# JSON Mode Analysis — Валидация использования

**Дата:** 2026-03-30  
**Статус:** ✅ Валидация завершена  
**Вывод:** JSON mode используется **ТОЛЬКО** для `translate_metadata()`, не для основного перевода

---

## 📊 Результаты валидации

### Где используется JSON mode:

| Функция | JSON mode | Зачем | Критичность |
|---------|-----------|-------|-------------|
| **`translate_metadata()`** | ✅ `True` | Получить JSON ответ для метаданных книги | ⚠️ **Используется** |
| `initial_translation()` | ❌ `False` (default) | Перевод текста | ✅ Не нужен |
| `reflection()` | ❌ `False` (default) | Анализ качества | ✅ Не нужен |
| `improve_translation()` | ❌ `False` (default) | Редактирование | ✅ Не нужен |
| `final_edit()` | ❌ `False` (default) | Вычитка | ✅ Не нужен |
| `generate_synopsis()` | ❌ `False` (default) | Синопсис | ✅ Не нужен |
| `vocabulary()` | ❌ `False` (default) | Перевод терминов | ✅ Не нужен |

---

## 🔍 Детальный анализ

### 1. `translate_metadata()` — ЕДИНСТВЕННОЕ использование

**Файл:** `src/utils.py`, строка 1406

```python
def translate_metadata(metadata: dict, source_lang: str, target_lang: str,
                       country: str) -> dict:
    """Translate metadata dictionary using LLM in JSON mode."""
    
    response = llm_service_compat.get_completion(
        role="Proofread",
        prompt_category="metadata_translation",
        prompt_key=prompt_key,
        json_mode=True,  # ← ЕДИНСТВЕННОЕ использование
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        metadata_json=json.dumps(metadata, ensure_ascii=False)
    )
    
    # Extract JSON from response
    match = re.search(r'(\{.*\})', response, re.DOTALL)
    clean_json = match.group(1) if match else response.strip()
    
    return json.loads(clean_json)
```

**Зачем нужен JSON mode:**
- LLM должен вернуть **валидный JSON** с переведёнными метаданными
- Пример входа: `{"book-title": "Alice", "author": "Lewis Carroll"}`
- Пример выхода: `{"book-title": "Алиса", "author": "Льюис Кэрролл"}`

**Промпт:**
```
<metadata>
{"book-title": "Alice", "author": "Lewis Carroll"}
</metadata>

Translate all values to russian. Localize author names appropriately. 
Preserve JSON structure. Output only valid JSON.
```

**Критичность:**
- ⚠️ **Средняя** — используется только для перевода метаданных (1 раз за книгу)
- ❌ **Не критично** для основного перевода
- ✅ Можно заменить на парсинг plain text если JSON mode не работает

---

### 2. Основной перевод — JSON mode НЕ используется

**Файл:** `src/utils.py`, строки 588-640

```python
text, tokens_used = llm_service.complete(
    role=LLMRole.PRIMARY,
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    max_tokens=MAX_TOKENS_PER_CHUNK,
    # json_mode НЕ передаётся → по умолчанию False
)
```

**Формат ответа:**
- ❌ **НЕ JSON**
- ✅ **Plain text** в wrapper-тэгах: `<ttext>...</ttext>`

**Промпт:**
```
Translate the text inside <source> to russian.

CRITICAL REQUIREMENTS:
1. PRESERVE ALL XML TAGS EXACTLY
2. Apply vocabulary terms where applicable

Output ONLY the translated text wrapped in <ttext>...</ttext>
```

**Извлечение:**
```python
# remove_tags() извлекает из wrapper-тэгов
def remove_tags(text: str) -> str:
    # Try to extract from <ttext> wrapper
    ttext_match = re.search(r'<ttext[^>]*>([\s\S]*?)</ttext>', text)
    if ttext_match:
        return ttext_match.group(1).strip()
    
    # Fallback: return full text
    return text.strip()
```

---

## 🎯 Конфигурация JSON mode

### Переменные окружения:

```bash
# .env
DISABLE_JSON_MODE_TRANSLATE=true   # По умолчанию: отключен
DISABLE_JSON_MODE_PROOFREAD=true   # По умолчанию: отключен
```

### Логика в коде:

**Файл:** `src/utils.py`, строки 449-454

```python
if role == LLMRole.PRIMARY:
    disable_json = config.disable_json_mode_translate
else:
    disable_json = config.disable_json_mode_proofread

if disable_json and json_mode:
    json_mode = False  # Принудительное отключение
```

**Что происходит:**
1. Если `DISABLE_JSON_MODE_TRANSLATE=true` → JSON mode **отключен** для Primary LLM
2. Если `DISABLE_JSON_MODE_PROOFREAD=true` → JSON mode **отключен** для Secondary LLM
3. Даже если `json_mode=True` передан в функцию, он будет **переопределён** на `False`

---

## 📈 Статистика использования

| Компонент | Вызовов за книгу | JSON mode | Влияние |
|-----------|------------------|-----------|---------|
| **metadata_translation** | 1 | ✅ `True` | ⚠️ Только метаданные |
| **initial_translation** | 100-1000 | ❌ `False` | ✅ Основной перевод |
| **reflection** | 100-1000 | ❌ `False` | ✅ Анализ качества |
| **improve_translation** | 100-1000 | ❌ `False` | ✅ Редактирование |
| **final_edit** | 100-1000 | ❌ `False` | ✅ Вычитка |
| **synopsis** | 100-1000 | ❌ `False` | ✅ Контекст |
| **vocabulary** | 0-1 | ❌ `False` | ✅ Словарь |

**Итого:**
- JSON mode используется **1 раз** за книгу (метаданные)
- **99.9%** переводов работают **БЕЗ JSON mode**

---

## ⚠️ Проблемы с JSON mode

### Известные проблемы локальных LLM:

| Модель | JSON mode | Проблема |
|--------|-----------|----------|
| **Gemma 2/3** | ❌ Не работает | Возвращает пустой ответ |
| **Mistral** | ❌ Не работает | Может возвращать пустой ответ |
| **Llama 3.x** | ❌ Не работает | Локальные версии часто fail |
| **Hunyuan** | ✅ Работает | Поддерживает корректно |
| **Qwen** | ✅ Работает | Поддерживает корректно |
| **OpenAI/GPT** | ✅ Работает | Поддерживает корректно |

### Рекомендации из кода:

**Файл:** `src/config.py`, строки 28-29

```python
self.disable_json_mode_translate = os.getenv('DISABLE_JSON_MODE_TRANSLATE', 'true').lower() in ['true', '1', 't', 'on', 'yes']
self.disable_json_mode_proofread = os.getenv('DISABLE_JSON_MODE_PROOFREAD', 'true').lower() in ['true', '1', 't', 'on', 'yes']
```

**По умолчанию:** `true` (отключен) — **безопаснее для локальных LLM**

---

## 🔧 Выводы и рекомендации

### ✅ Текущая конфигурация корректна:

```bash
# .env (по умолчанию)
DISABLE_JSON_MODE_TRANSLATE=true   # ✅ Отключен для локальных LLM
DISABLE_JSON_MODE_PROOFREAD=true   # ✅ Отключен для локальных LLM
```

### ⚠️ JSON mode нужен ТОЛЬКО для:

```python
translate_metadata()  # 1 раз за книгу
```

### 📋 Рекомендации:

1. **Оставить по умолчанию `DISABLE_JSON_MODE_* = true`**
   - Безопаснее для локальных LLM
   - Не влияет на основной перевод
   - Влияет только на метаданные (1 раз)

2. **Если JSON mode нужен для metadata:**
   - Использовать API модели (Hunyuan, Qwen, GPT)
   - Или установить `DISABLE_JSON_MODE_PROOFREAD=false`

3. **Если JSON mode не работает:**
   - `translate_metadata()` вернёт оригинальные метаданные (fallback)
   - Основной перевод **не пострадает**

---

## 📝 Changelog

- **2026-03-30:** Initial analysis — JSON mode используется только для metadata
- **v1.0:** Валидация завершена

---

**См. также:**
- [README.md#json-mode-control](../README.md#-json-mode-control)
- [src/utils.py#translate_metadata](../src/utils.py#L1398)
- [src/config.py#disable_json_mode](../src/config.py#L28)
