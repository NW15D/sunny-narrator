# JSON-режим для LLM ответов Implementation Plan

**Goal:** Устранить ошибки извлечения перевода из LLM ответа путём использования JSON-формата вместо XML-тегов.

**Architecture:** Добавить JSON-режим работы с LLM, где вход и выход структурированы в JSON. Это устраняет проблему удаления нужного контекста при очистке от XML-тегов.

**Tech Stack:** Python, JSON, регулярные выражения, LLM API

**Execution:** Используйте `executing-plans` или `subagent-driven-development` skill

---

## Task 1: Создать тесты JSON парсинга (ПЕРЕД реализацией - TDD)

**Files:**
- Create: `tests/test_json_mode.py`

- [ ] **Step 1: Написать тест (RED phase)**
```python
import pytest
from src.utils import parse_json_response

def test_parse_json_translation():
    text = '{"translation": "переведенный текст"}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert result == "переведенный текст"

def test_parse_json_with_wrapper():
    text = 'Here is your translation: {"translation": "text"}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert result == "text"

def test_parse_json_suggestions():
    text = '{"suggestions": ["Fix this", "Change that"]}'
    result, is_json = parse_json_response(text)
    assert is_json is True
    assert isinstance(result, list)

def test_parse_invalid_json_returns_original():
    text = "Just plain text without JSON"
    result, is_json = parse_json_response(text)
    assert is_json is False
    assert result == "Just plain text without JSON"
```

- [ ] **Step 2: Запустить тест (должен упасть)**
```bash
cd ~/prj/sunny-narrator && python -m pytest tests/test_json_mode.py -v
```
Expected: FAIL (функция parse_json_response не существует)

- [ ] **Step 3: Commit (RED)**
```bash
cd ~/prj/sunny-narrator && git add tests/test_json_mode.py && git commit -m "TDD: add JSON parsing tests (RED)"
```

---

## Task 2: Обновить конфигурацию (config.py)

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Добавить json_mode в config.py**
```python
# Добавить после существующих полей (около строки 30):
self.json_mode = os.getenv('JSON_MODE', 'false').lower() in ['true', '1', 't', 'on', 'yes']
```

- [ ] **Step 2: Проверить импорт os**
```bash
grep -n "^import os" src/config.py
```

- [ ] **Step 3: Запустить тест**
```bash
cd ~/prj/sunny-narrator && python -c "from src.config import config; print(f'JSON_MODE: {config.json_mode}')"
```
Expected: `JSON_MODE: False` (по умолчанию)

- [ ] **Step 4: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/config.py && git commit -m "config: add JSON_MODE flag"
```

---

## Task 3: Добавить JSON-промты (prompts.json)

**Files:**
- Modify: `src/prompts.json`

- [ ] **Step 1: Добавить JSON-промты для initial_translation**
```json
"initial_translation_json": {
    "system": "You are a professional literary translator. Translate text accurately. Output ONLY valid JSON with a \"translation\" key. DO NOT output explanations or any other text. Example: {\"translation\": \"translated text here\"}",
    "user_text": "{json_input}\n\nOutput ONLY valid JSON: {\"translation\": \"...\"}",
    "user_xml": "{json_input}\n\nOutput ONLY valid JSON: {\"translation\": \"...\"}",
    "user_hunyuan": "{json_input}\n\nOutput: {\"translation\": \"...\"}"
}
```

**Note:** json_input формируется в коде и содержит:
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

- [ ] **Step 2: Добавить JSON-промты для reflection**
```json
"reflection_json": {
    "system": "You are a literary translation quality reviewer. Review the translation and provide suggestions in JSON format. Output ONLY valid JSON with a \"suggestions\" key - a list of numbered suggestions. Example: {\"suggestions\": [\"Fix X\", \"Change Y\"]}",
    "user_text": "Review translation to {target_lang} for {country}.\n\nVocabulary: {vocab_dict}\n\nSource:\n{source_text}\n\nTranslation:\n{translation}\n\nOutput JSON with suggestions list: {\"suggestions\": [\"...\"]}",
    "user_xml": "Review translation to {target_lang} for {country}.\n\nVocabulary: {vocab_dict}\n\nSource (with XML): {source_text}\n\nTranslation: {translation}\n\nOutput: {\"suggestions\": [\"...\"]}"
}
```

- [ ] **Step 3: Добавить JSON-промты для improve**
```json
"improve_json": {
    "system": "You are a literary translation editor. Apply suggestions to improve translation. Output ONLY valid JSON with \"translation\" key. Example: {\"translation\": \"improved text\"}",
    "user_text": "Apply suggestions to improve translation to {target_lang} for {country}.\n\nVocabulary: {vocab_dict}\n\nCurrent translation:\n{translation}\n\nSuggestions:\n{suggestion_list}\n\nOutput: {\"translation\": \"...\"}",
    "user_xml": "Apply suggestions to improve translation to {target_lang} for {country}.\n\nVocabulary: {vocab_dict}\n\nTranslation: {translation}\n\nSuggestions: {suggestion_list}\n\nOutput: {\"translation\": \"...\"}"
}
```

- [ ] **Step 4: Добавить JSON-промты для editor (final_edit)**
```json
"editor_json": {
    "system": "You are a professional translation editor. Perform final proofreading. Output ONLY valid JSON with \"translation\" key. Example: {\"translation\": \"final text\"}",
    "user_text": "Final proofread to {target_lang} for {country}.\n\nTranslation:\n{translation}\n\nOutput: {\"translation\": \"...\"}",
    "user_xml": "Final proofread to {target_lang} for {country}.\n\nTranslation (preserve XML): {translation}\n\nOutput: {\"translation\": \"...\"}",
    "user_hunyuan": "Final proofread to {target_lang}.\n\n{translation}\n\nOutput: {\"translation\": \"...\"}"
}
```

- [ ] **Step 5: Валидировать JSON**
```bash
cd ~/prj/sunny-narrator && python -c "import json; json.load(open('src/prompts.json'))" && echo "Valid JSON"
```

- [ ] **Step 6: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/prompts.json && git commit -m "prompts: add JSON format prompts for all stages"
```

---

## Task 4: Модифицировать парсинг (utils.py) — GREEN phase

**Files:**
- Modify: `src/utils.py:1184-1280` (функция remove_tags и remove_tags_with_check)

- [ ] **Step 1: Добавить функцию parse_json_response**
```python
def parse_json_response(text: str) -> tuple:
    """
    Parse JSON response from LLM.
    Returns: (result: str, success: bool)
    
    Priority:
    1. Find first valid JSON block
    2. Extract translation or suggestions
    3. Fallback to non-JSON if invalid
    """
    if not text:
        return "", False
    
    # Try to find JSON block (handles conversational wrappers)
    json_match = re.search(r'(\{[\s\S]*?\})', text)
    if not json_match:
        return text.strip(), False  # No JSON found, return as-is
    
    try:
        data = json.loads(json_match.group(1))
        
        # Check for translation
        if 'translation' in data and data['translation']:
            return data['translation'].strip(), True
        
        # Check for suggestions (reflection stage)
        if 'suggestions' in data:
            if isinstance(data['suggestions'], list):
                return data['suggestions'], True
            elif isinstance(data['suggestions'], str):
                return data['suggestions'], True
        
        # JSON found but no valid content
        return text.strip(), False
        
    except (json.JSONDecodeError, KeyError):
        # Invalid JSON, return original text
        return text.strip(), False
```

- [ ] **Step 2: Модифицировать remove_tags_with_check**
Добавить в начало функции (после проверки на пустой text):
```python
    # PRIORITY 1: Try JSON parsing first
    parsed, is_json = parse_json_response(text)
    if is_json and parsed:
        logger.debug(f"Extracted content from JSON response [{stage_name}]")
        return parsed
    
    # If JSON parsing failed, fall back to original logic
    # (rest of the existing function)
```

- [ ] **Step 3: Проверить импорт json**
```bash
grep -n "^import json" src/utils.py
```

- [ ] **Step 4: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/utils.py && git commit -m "utils: add JSON parsing in remove_tags_with_check"
```

---

## Task 5.1: Обновить initial_translation для JSON mode

**Files:**
- Modify: `src/utils.py:574-670` (функция initial_translation)

- [ ] **Step 1: Добавить формирование json_input**
```python
import json

# Внутри initial_translation, перед вызовом llm_service.complete:
json_input = json.dumps({
    "source": context.source_text,
    "source_lang": context.source_lang,
    "target_lang": context.target_lang,
    "country": context.country,
    "vocabulary": context.vocab_dict or {},
    "synopsis": context.outline_text or ""
}, ensure_ascii=False)

if config.json_mode:
    user_prompt = config.get_prompt(
        "initial_translation", "user_text_json",
        json_input=json_input
    )
    system_prompt = config.get_prompt("initial_translation", "system_json")
    json_mode = True
else:
    # ... existing code
```

- [ ] **Step 2: Проверить что работает**
```bash
cd ~/prj/sunny-narrator && python -c "from src.utils import TranslationPipeline; print('OK')"
```

- [ ] **Step 3: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/utils.py && git commit -m "utils: add JSON mode to initial_translation"
```

---

## Task 5.2: Обновить reflection для JSON mode

**Files:**
- Modify: `src/utils.py:719-760` (функция reflection)

- [ ] **Step 1: Добавить json_input формирование**
```python
json_input = json.dumps({
    "source": context.source_text,
    "translation": translation,
    "source_lang": context.source_lang,
    "target_lang": context.target_lang,
    "country": context.country,
    "vocabulary": context.vocab_dict or {}
}, ensure_ascii=False)

if config.json_mode:
    user_prompt = config.get_prompt(
        "reflection", "user_text_json",
        json_input=json_input
    )
    system_prompt = config.get_prompt("reflection", "system_json")
    json_mode = True
```

- [ ] **Step 2: Обновить обработку результата**
В remove_tags_with_check добавить обработку suggestions:
```python
# После remove_tags_with_check в reflection:
if not text or len(text.strip()) == 0:
    # Treat empty suggestions as empty list, not error
    logger.debug("Empty reflection suggestions")
    text = []
elif isinstance(text, list):
    # Already parsed as suggestions list
    pass
```

- [ ] **Step 3: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/utils.py && git commit -m "utils: add JSON mode to reflection"
```

---

## Task 5.3: Обновить improve_translation для JSON mode

**Files:**
- Modify: `src/utils.py:758-810` (функция improve_translation)

- [ ] **Step 1: Добавить json_input**
```python
json_input = json.dumps({
    "translation": translation,
    "suggestions": reflection if isinstance(reflection, list) else reflection.split('\n'),
    "target_lang": context.target_lang,
    "country": context.country,
    "vocabulary": context.vocab_dict or {}
}, ensure_ascii=False)

if config.json_mode:
    user_prompt = config.get_prompt(
        "improve", "user_text_json",
        json_input=json_input
    )
    system_prompt = config.get_prompt("improve", "system_json")
    json_mode = True
```

- [ ] **Step 2: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/utils.py && git commit -m "utils: add JSON mode to improve_translation"
```

---

## Task 5.4: Обновить final_edit для JSON mode

**Files:**
- Modify: `src/utils.py:806-860` (функция final_edit)

- [ ] **Step 1: Добавить json_input**
```python
json_input = json.dumps({
    "translation": translation,
    "target_lang": context.target_lang,
    "country": context.country
}, ensure_ascii=False)

if config.json_mode:
    user_prompt = config.get_prompt(
        "editor", "user_text_json",
        json_input=json_input
    )
    system_prompt = config.get_prompt("editor", "system_json")
    json_mode = True
```

- [ ] **Step 2: Commit**
```bash
cd ~/prj/sunny-narrator && git add src/utils.py && git commit -m "utils: add JSON mode to final_edit"
```

---

### Task 6.1: Обновить .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Добавить JSON_MODE**
echo -e "\n# JSON mode for LLM responses (more reliable parsing)\nJSON_MODE=false" >> .env.example

- [ ] **Step 2: Commit**
```bash
cd ~/prj/sunny-narrator && git add .env.example && git commit -m "config: add JSON_MODE to .env.example"
```

---

## Task 6.2: Интеграционные тесты

**Files:**
- Modify: `tests/test_json_mode.py`

- [ ] **Step 1: Добавить интеграционные тесты**
```python
def test_config_json_mode_flag():
    """Test that JSON_MODE flag is read from config"""
    from src.config import Config
    import os
    
    # Save original
    orig = os.environ.get('JSON_MODE')
    
    os.environ['JSON_MODE'] = 'true'
    config = Config()
    assert config.json_mode is True
    
    os.environ['JSON_MODE'] = 'false'
    config = Config()
    assert config.json_mode is False
    
    # Restore
    if orig:
        os.environ['JSON_MODE'] = orig
    else:
        os.environ.pop('JSON_MODE', None)
```

- [ ] **Step 2: Запустить все тесты**
```bash
cd ~/prj/sunny-narrator && python -m pytest tests/test_json_mode.py -v
```

- [ ] **Step 3: Commit**
```bash
cd ~/prj/sunny-narrator && git add tests/test_json_mode.py && git commit -m "tests: add integration tests for JSON mode"
```

---

## Task 7: Добавить документацию

**Files:**
- Modify: `docs/PROMPTS_GUIDE.md` (создать если нет)

- [ ] **Step 1: Добавить секцию о JSON режиме**
```markdown
## JSON Mode

Set `JSON_MODE=true` in `.env` to use JSON format for LLM responses.

### Benefits
- More reliable parsing (no XML tag conflicts)
- Structured input/output
- Better error handling

### Format
See `specs/2026-04-28-json-llm-response-design.md`
```

- [ ] **Step 2: Commit**
```bash
cd ~/prj/sunny-narrator && git add docs/ && git commit -m "docs: add JSON mode documentation"
```
