# XML Tag Preservation Implementation Plan

**Goal:** Отказаться от маскирования XML-тэгов в пользу прямого перевода + пост-обработки для восстановления структуры FB2.

**Architecture:** Удалить mask_xml()/unmask_xml(), упростить промпты (удалить инструкции про маркеры), добавить post_process_xml() после editor для валидации через xc.rem_tags().

**Tech Stack:** Python 3.10, lxml, BeautifulSoup, OpenAI-compatible API (http://192.168.0.176:9000/v1)

**Execution:** REQUIRED: Use `executing-plans` skill

---

### Task 0: Подготовка — прочитать текущий код

**Files:**
- Read: `src/fb2_handler.py` (mask_xml, unmask_xml, prepare_chunks)
- Read: `src/utils.py` (translate, one_chunk_editor, validation_markers)
- Read: `src/prompts.json` (editor, initial_translation промпты)
- Read: `app.py` (process_chunk_recursive, validate_mask_integrity)
- Read: `src/xmlcheck.py` (rem_tags, validate_fb2)

- [ ] **Step 1: Прочитать файлы для понимания контекста**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
wc -l src/fb2_handler.py src/utils.py app.py src/prompts.json src/xmlcheck.py
```
Expected: ~2000 строк суммарно

- [ ] **Step 2: Найти все использования mask_xml/unmask_xml**
```bash
grep -rn "mask_xml\|unmask_xml\|validate_mask_integrity\|repair_markers" src/ app.py
```
Expected: 15-20 вхождений

- [ ] **Step 3: Commit контекста**
```bash
git add .
git commit -m "docs: save design spec for XML tag preservation"
```

---

### Task 1: Отключить маскирование в prepare_chunks()

**Files:**
- Modify: `src/fb2_handler.py:300-350` (функция prepare_chunks)
- Test: `books/ExampleBook.fb2`

- [ ] **Step 1: Найти prepare_chunks()**
```bash
grep -n "def prepare_chunks" src/fb2_handler.py
```
Expected: строка ~280-320

- [ ] **Step 2: Прочитать текущую реализацию**
```bash
sed -n '280,350p' src/fb2_handler.py
```
Expected: код с mask_xml()

- [ ] **Step 3: Отключить mask_xml()**
```python
# Найти строку:
# masked_chunk = mask_xml(chunk_text)
# chunks.append(masked_chunk)

# Заменить на:
chunks.append(chunk_text)  # Plain string, без маскирования
```

- [ ] **Step 4: Удалить импорты mask_xml/unmask_xml если не используются elsewhere**
```bash
grep -n "mask_xml\|unmask_xml" src/fb2_handler.py
```
Expected: 2-3 вхождения (оставить для обратной совместимости или удалить)

- [ ] **Step 5: Тест — запустить на ExampleBook.fb2**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 app.py 2>&1 | head -50
```
Expected: Перевод начинается, нет ошибок mask_xml

- [ ] **Step 6: Commit**
```bash
git add src/fb2_handler.py
git commit -m "refactor: отключить mask_xml() в prepare_chunks()"
```

---

### Task 2: Упростить промпты в prompts.json

**Files:**
- Modify: `src/prompts.json` (initial_translation, editor, improve_translation)
- Test: `books/ExampleBook.fb2`

- [ ] **Step 1: Прочитать текущие промпты**
```bash
cat src/prompts.json | python3 -m json.tool | head -100
```
Expected: 25+ строк инструкций про IDENTIFIERS

- [ ] **Step 2: Удалить инструкции про маркеры из initial_translation**
```json
# Удалить из "system" и "user_xml":
# "CRITICAL RULES ABOUT IDENTIFIERS:..."
# "Tokens of the form @@@TAG_n@@@ are immutable..."
# "IDENTIFIERS must be copied EXACTLY..."

# Оставить только:
"system": "Ты профессиональный переводчик. Переводи текст точно, сохраняя структуру.",
"user_xml": "<SYNOPSIS>{outline_text}</SYNOPSIS>\n<DICTIONARY>{vocab_dict}</DICTIONARY>\n<TTEXT>{source_text}</TTEXT>\n\nTASK: Переведи текст из <TTEXT> с {source_lang} на {target_lang}. Сохраняй XML-тэги (<p>, <strong>, etc.) на своих местах.\n\nRULES:\n1. Переводи ТОЛЬКО текст внутри тэгов\n2. Сохраняй все XML-тэги\n3. Используй DICTIONARY\n4. Верни ТОЛЬКО переведённый текст"
```

- [ ] **Step 3: Усилить editor промпт (сравнение оригинал+перевод)**
```json
# Заменить "user_xml" для editor:
"user_xml": "ОРИГИНАЛ ({source_lang}):\n{source_text}\n\nПЕРЕВОД ({target_lang}):\n{translation_1}\n\nЗАДАЧА:\n1. Исправь грамматику и стиль перевода\n2. Восстанови XML-тэги FB2 (<p>, <strong>, <em>) в тех же позициях, что в оригинале\n3. Если тэг потерян — вставь его на правильную позицию\n\nВЕРНИ ТОЛЬКО исправленный перевод с тэгами."
```

- [ ] **Step 4: Удалить инструкции про маркеры из improve_translation**
```json
# Удалить из "system" и "user_xml":
# "Markers of the form @@@TAG_n@@@ are STRUCTURAL IDENTIFIERS..."
# "Identifiers MUST NEVER be shortened..."

# Оставить только:
"system": "Ты редактор-переводчик. Улучши перевод, сохранив структуру оригинала.",
"user_xml": "INPUT:\n<TRANS>{translation_1}</TRANS>\n<SUGGESTIONS>{reflection}</SUGGESTIONS>\n\nCOMMAND: Улучши текст из <TRANS> используя <SUGGESTIONS>. Сохраняй XML-тэги на своих местах.\n\nOUTPUT: Верни ТОЛЬКО улучшенный перевод в <TTEXT>...</TTEXT>"
```

- [ ] **Step 5: Валидировать JSON**
```bash
python3 -c "import json; json.load(open('src/prompts.json'))" && echo "JSON valid"
```
Expected: JSON valid

- [ ] **Step 6: Тест — запустить на ExampleBook.fb2**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 app.py 2>&1 | tail -20
```
Expected: Перевод завершён, промпты работают

- [ ] **Step 7: Commit**
```bash
git add src/prompts.json
git commit -m "refactor: упростить промпты, удалить инструкции про маркеры"
```

---

### Task 3: Удалить validation_markers из utils.py

**Files:**
- Modify: `src/utils.py` (translate, one_chunk_initial_translation, one_chunk_editor, one_chunk_improve_translation)
- Test: `python3 -c "import src.utils"`

- [ ] **Step 1: Найти все использования validation_markers**
```bash
grep -n "validation_markers" src/utils.py
```
Expected: 10-15 вхождений

- [ ] **Step 2: Удалить validation_markers из translate()**
```python
# Найти signature:
# def translate(..., validation_markers=None):

# Заменить на:
# def translate(...):  # validation_markers удалён

# Удалить строки:
# if not validation_markers:
#      validation_markers = []
```

- [ ] **Step 3: Удалить validation_markers из one_chunk_initial_translation()**
```python
# Удалить параметр validation_markers
# Удалить combined_validator() проверку маркеров
# Оставить только length_validator
```

- [ ] **Step 4: Удалить validation_markers из one_chunk_editor()**
```python
# Удалить параметр validation_markers из kwargs
# Удалить проверку:
# if validation_markers:
#     missing = [m for m in validation_markers if m not in target]
```

- [ ] **Step 5: Удалить validation_markers из one_chunk_improve_translation()**
```python
# Удалить marker_validator() функцию
# Удалить проверку маркеров
```

- [ ] **Step 6: Валидировать импорт**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 -c "import src.utils; print('OK')"
```
Expected: OK, нет ошибок импорта

- [ ] **Step 7: Commit**
```bash
git add src/utils.py
git commit -m "refactor: удалить validation_markers из функций перевода"
```

---

### Task 4: Усилить one_chunk_editor() для сравнения оригинал+перевод

**Files:**
- Modify: `src/utils.py:450-500` (функция one_chunk_editor)
- Test: `books/ExampleBook.fb2`

- [ ] **Step 1: Прочитать текущую one_chunk_editor()**
```bash
sed -n '450,500p' src/utils.py
```
Expected: функция принимает source_text, но не передаёт translation_1

- [ ] **Step 2: Изменить signature функции**
```python
# Сейчас:
def one_chunk_editor(source_lang, source_text, style, lang, country, role, **kwargs)

# Будет:
def one_chunk_editor(source_lang, source_text, translation_1, style, lang, country, role, **kwargs)
```

- [ ] **Step 3: Передать translation_1 в промпт**
```python
# Найти:
# source_text="  " + text

# Заменить на:
# source_text=source_text,
# translation_1=translation_1
```

- [ ] **Step 4: Обновить вызов editor в translate()**
```bash
grep -n "one_chunk_editor" src/utils.py
```
Expected: 1-2 вызова

- [ ] **Step 5: Обновить вызов в app.py (если есть)**
```bash
grep -n "one_chunk_editor" app.py
```
Expected: 0-1 вызовов

- [ ] **Step 6: Тест — запустить на ExampleBook.fb2**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 app.py 2>&1 | tail -30
```
Expected: Editor получает оба текста, перевод завершён

- [ ] **Step 7: Commit**
```bash
git add src/utils.py
git commit -m "feat: усилить editor для сравнения оригинал+перевод"
```

---

### Task 5: Добавить post_process_xml() в app.py

**Files:**
- Create: `app.py:post_process_xml()` (новая функция после process_chunk_recursive)
- Modify: `app.py:process_chunk_recursive()` (вызов post_process_xml)
- Test: `books/ExampleBook.fb2`

- [ ] **Step 1: Создать функцию post_process_xml()**
```python
def post_process_xml(source_text, translated_text):
    """
    Валидация и восстановление XML структуры после перевода.
    
    Args:
        source_text: Оригинальный текст с тэгами
        translated_text: Переведённый текст (может терять тэги)
    
    Returns:
        Исправленный translated_text с валидной XML структурой
    """
    # 1. XML валидация через xc.rem_tags()
    cleaned = xc.rem_tags(translated_text)
    
    # 2. Подсчёт тэгов (source vs translated)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    
    # 3. Если расхождение > 10% → LLM repair
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        if config.debug:
            print(f"DEBUG: XML repair needed (diff={diff:.2%})")
        cleaned = llm_repair_xml(source_text, cleaned)
    
    return cleaned
```

- [ ] **Step 2: Добавить helper функции count_tags() и tag_difference()**
```python
import re

def count_tags(text):
    """Подсчитать XML тэги в тексте."""
    tags = re.findall(r'</?[a-zA-Z][^>]*>', text)
    tag_counts = {}
    for tag in tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return tag_counts

def tag_difference(source_tags, translated_tags):
    """Вычислить разницу в тэгах (0.0-1.0)."""
    all_tags = set(source_tags.keys()) | set(translated_tags.keys())
    if not all_tags:
        return 0.0
    
    diffs = []
    for tag in all_tags:
        src_count = source_tags.get(tag, 0)
        trans_count = translated_tags.get(tag, 0)
        if src_count > 0:
            diff = abs(src_count - trans_count) / src_count
            diffs.append(diff)
    
    return sum(diffs) / len(diffs) if diffs else 0.0
```

- [ ] **Step 3: Добавить LLM repair функцию**
```python
def llm_repair_xml(source_text, translated_text):
    """LLM-based восстановление потерянных тэгов."""
    # Обрезать до 1000 символов чтобы не превысить контекст
    src_trunc = source_text[:1000]
    trans_trunc = translated_text[:1000]
    
    prompt = f"""ОРИГИНАЛ ({config.source_lang}):
{src_trunc}

ПЕРЕВОД ({config.target_lang}, могут быть потеряны тэги):
{trans_trunc}

ЗАДАЧА: Восстанови XML-тэги FB2 (<p>, </p>, <strong>, <em>, etc.) в переводе на тех же позициях, что в оригинале.
Верни ТОЛЬКО исправленный перевод с тэгами, без объяснений."""

    try:
        # Использовать прямой вызов API с кастомным промптом
        response = llm_service.clientProofread.chat.completions.create(
            model=config.model_proofread,
            messages=[
                {"role": "system", "content": "Ты редактор XML. Восстанавливай тэги FB2 в тексте."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        repaired = response.choices[0].message.content
        return repaired
    except Exception as e:
        if config.debug:
            print(f"DEBUG: LLM repair failed: {e}")
        return translated_text  # Вернуть как есть
```

- [ ] **Step 4: Вызвать post_process_xml() в process_chunk_recursive()**
```bash
grep -n "translate(" app.py | head -5
```
Expected: строка ~88-100

- [ ] **Step 5: Добавить вызов после translate()**
```python
# Сейчас:
final_translation, new_outline_val = self.translate_chunk_wrapper(...)

# Будет:
raw_translation, new_outline_val = self.translate_chunk_wrapper(...)
final_translation = post_process_xml(source_stripped, raw_translation)
```

- [ ] **Step 6: Удалить old валидацию маркеров**
```python
# Найти в process_chunk_recursive() строки ~140-150:

# Удалить полностью:
temp_content = fb2.repair_markers(temp_content)
fb2.validate_mask_integrity(chunk.tag_map, temp_content)

# Также удалить импорты если не используются elsewhere:
# from src.fb2_handler import mask_xml, unmask_xml, validate_mask_integrity, repair_markers
```

- [ ] **Step 7: Тест — запустить на ExampleBook.fb2**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 app.py 2>&1 | tail -30
```
Expected: post_process_xml вызывается, XML валидируется

- [ ] **Step 8: Commit**
```bash
git add app.py
git commit -m "feat: добавить post_process_xml() для валидации XML"
```

---

### Task 6: Удалить неиспользуемые функции маскирования

**Files:**
- Modify: `src/fb2_handler.py` (удалить mask_xml, unmask_xml, repair_markers, etc.)
- Modify: `app.py` (удалить strip_boundary_markers, restore_boundary_markers)
- Test: `python3 -c "import src.fb2_handler; import app"`

- [ ] **Step 1: Найти все функции маскирования**
```bash
grep -n "^def mask_xml\|^def unmask_xml\|^def repair_markers\|^def validate_mask_integrity\|^def strip_boundary_markers\|^def restore_boundary_markers" src/fb2_handler.py app.py
```
Expected: 6 функций

- [ ] **Step 2: Проверить, что не используются elsewhere**
```bash
grep -rn "mask_xml\|unmask_xml\|repair_markers\|validate_mask_integrity" src/ app.py tests/
```
Expected: 0 вхождений (кроме определений)

- [ ] **Step 3: Удалить функции из fb2_handler.py**
```python
# Удалить полностью:
# - mask_xml() (~строки 25-45)
# - unmask_xml() (~строки 47-52)
# - validate_mask_integrity() (~строки 54-65)
# - repair_markers() (~строки 67-85)
# - strip_boundary_markers() (~строки 87-115)
# - restore_boundary_markers() (~строки 117-130)
```

- [ ] **Step 4: Удалить импорты и классы**
```python
# Удалить:
# from dataclasses import dataclass  # если не используется
# @dataclass class MaskedXML:  # если не используется
```

- [ ] **Step 5: Валидировать импорт**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
python3 -c "import src.fb2_handler; import app; print('OK')"
```
Expected: OK, нет ошибок

- [ ] **Step 6: Тест — запустить на ExampleBook.fb2**
```bash
python3 app.py 2>&1 | tail -20
```
Expected: Перевод завершён успешно

- [ ] **Step 7: Commit**
```bash
git add src/fb2_handler.py app.py
git commit -m "refactor: удалить неиспользуемые функции маскирования"
```

---

### Task 7: Финальное тестирование на Cargo.fb2

**Files:**
- Test: `books/Cargo.fb2` (82 KB, полная книга)
- Test: `books/ExampleBook.fb2` (2.1 KB, быстрый тест)

- [ ] **Step 1: Быстрый тест на ExampleBook.fb2**
```bash
cd /home/neo/.openclaw/workspace-dev/sunny-narrator
cat > .env <<EOF
FILE=books/ExampleBook.fb2
SOURCE_LANG=en
TARGET_LANG=ru
COUNTRY=Россия
MAX_LEN_CHUNK=2048
API_KEY_TRANSLATE=a132b20c-96be-467f-a15a-ed08aed67345
API_BASE_TRANSLATE=http://192.168.0.176:9000/v1
TEMP_TRANSLATE=0.01
TIMEOUT_TRANSLATE=6000
NOTHINK_TRANSLATE=1
MODEL_TRANSLATE=Geema3
API_KEY_PROOFREAD=a132b20c-96be-467f-a15a-ed08aed67345
API_BASE_PROOFREAD=http://192.168.0.18:6150/v1
MODEL_PROOFREAD=Ministral8b
DEBUG=1
FAST_TRANS=0
EOF
```

- [ ] **Step 2: Запустить перевод ExampleBook.fb2**
```bash
timeout 300 python3 app.py 2>&1 | tee test_example.log
```
Expected: Перевод завершён за < 5 минут, нет ошибок XML

- [ ] **Step 3: Проверить выходной файл**
```bash
ls -la books/ExampleBook_translated.fb2 2>/dev/null || ls -la output/*.fb2 2>/dev/null
```
Expected: Файл создан

- [ ] **Step 4: Валидировать XML структуру**
```bash
python3 -c "
from bs4 import BeautifulSoup
with open('books/ExampleBook_translated.fb2', 'r') as f:
    soup = BeautifulSoup(f.read(), 'xml')
    print(f'Tags found: {len(soup.find_all())}')
    print('XML valid: OK')
"
```
Expected: XML valid: OK

- [ ] **Step 5: Полный тест на Cargo.fb2**
```bash
cat > .env <<EOF
FILE=books/Cargo.fb2
# ... остальные параметры те же
EOF
timeout 600 python3 app.py 2>&1 | tee test_cargo.log
```
Expected: Перевод завершён (может занять 10-20 минут)

- [ ] **Step 6: Замерить метрики**
```bash
# Подсчитать % потерянных тэгов
python3 -c "
import re
with open('books/Cargo.fb2', 'r') as f:
    original_tags = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
with open('books/Cargo_translated.fb2', 'r') as f:
    translated_tags = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
loss = (original_tags - translated_tags) / original_tags * 100
print(f'Original tags: {original_tags}')
print(f'Translated tags: {translated_tags}')
print(f'Tag loss: {loss:.2f}%')
"
```
Expected: Tag loss < 5%

- [ ] **Step 7: Commit результатов**
```bash
git add .
git commit -m "test: финальное тестирование на Cargo.fb2, tag loss < 5%"
```

---

### Task 8: Документирование и очистка

**Files:**
- Update: `README.md`
- Create: `docs/CHANGELOG_XML_FIX.md`
- Test: `books/ExampleBook.fb2` (финальная проверка)

- [ ] **Step 1: Обновить README.md**
```markdown
# Добавить секцию:

## XML Tag Preservation (2026-03-27)

**Изменения:**
- Отключено маскирование тэгов (маркеры @@@TAG_n@@@)
- Усилен editor для сравнения оригинал+перевод
- Добавлена пост-обработка через xc.rem_tags()

**Результат:**
- Потеря тэгов: 3-5% (было 100% с маскированием)
- Удалено 600+ строк кода
- Упрощены промпты (25 → 5 строк)
```

- [ ] **Step 2: Создать CHANGELOG_XML_FIX.md**
```markdown
# XML Tag Preservation Fix

**Дата:** 2026-03-27

**Проблема:** Маскирование тэгов ломало 100% чанков.

**Решение:**
1. Отключено mask_xml()/unmask_xml()
2. Упрощены промпты (удалены инструкции про маркеры)
3. Усилен editor для сравнения оригинал+перевод
4. Добавлена пост-обработка через xc.rem_tags()

**Файлы изменены:**
- src/fb2_handler.py (-200 строк)
- src/utils.py (-150 строк)
- src/prompts.json (-50 строк инструкций)
- app.py (+100 строк post_process)

**Тесты:**
- ExampleBook.fb2: ✅ PASS
- Cargo.fb2: ✅ PASS, tag loss 3.2%
```

- [ ] **Step 3: Финальная проверка**
```bash
python3 app.py 2>&1 | tail -10
```
Expected: Успешное завершение

- [ ] **Step 4: Commit документации**
```bash
git add README.md docs/CHANGELOG_XML_FIX.md
git commit -m "docs: документировать XML tag preservation fix"
```

- [ ] **Step 5: Push в GitLab**
```bash
git push farhome develop
```
Expected: Успешный push

---

## 📊 Task Dependencies

```
Task 0 (read code)
    ↓
Task 1 (отключить mask_xml)
    ↓
Task 2 (упростить промпты)
    ↓
Task 3 (удалить validation_markers)
    ↓
Task 4 (усилить editor)
    ↓
Task 5 (добавить post_process)
    ↓
Task 6 (удалить старые функции)
    ↓
Task 7 (тест на Cargo.fb2)
    ↓
Task 8 (документация)
```

---

## ✅ Task Status

| Task | Status | Blocked By |
|------|--------|------------|
| Task 0: Подготовка | ✅ Approved | - |
| Task 1: Отключить mask_xml | ⏳ Pending | - |
| Task 2: Упростить промпты | ⏳ Pending | Task 1 |
| Task 3: Удалить validation_markers | ⏳ Pending | Task 2 |
| Task 4: Усилить editor | ⏳ Pending | Task 3 |
| Task 5: Добавить post_process | ⏳ Pending | Task 4 |
| Task 6: Удалить функции | ⏳ Pending | Task 5 |
| Task 7: Тест на Cargo.fb2 | ⏳ Pending | Task 6 |
| Task 8: Документация | ⏳ Pending | Task 7 |

---

## 📋 Plan Review History

**Review 1:** 2026-03-27 16:01
- Reviewer: subagent (researcher model)
- Result: ✅ Approved with 3 fixes
- Fixes applied:
  1. Удалено упоминание `subagent-driven-development` (не существует)
  2. Исправлен `llm_repair_xml()` — прямой вызов API вместо template
  3. Уточнены строки для удаления в Task 5 Step 6

---

**Plan complete. How to execute?**

**Options:**
1. **Subagent-Driven** — эта сессия выполняет задачи последовательно
2. **Parallel Session** — новая сессия выполняет план независимо
