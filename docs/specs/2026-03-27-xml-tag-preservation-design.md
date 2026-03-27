# XML Tag Preservation Design — Sunny Narrator

**Дата:** 2026-03-27  
**Статус:** Approved  
**Автор:** Dev + Nick

---

## 🎯 Goal

Отказаться от маскирования XML-тэгов (маркеры `@@@TAG_n@@@`) в пользу прямого перевода с тэгами + пост-обработки для восстановления структуры FB2.

**Проблема:** Текущее маскирование ломает 100% чанков, хотя без маскирования потери только 3-5%.

---

## 📐 Architecture

### Текущая архитектура (с маскированием)

```
chunk → mask_xml() → translate() → editor() → unmask_xml() → validate()
```

**Проблемы:**
- Маркеры `@@@TAG_n@@@` не являются естественными токенами для LLM
- 20% токенов тратится на маркеры
- 651 строка кода для маскирования/валидации/ремонта
- 100% чанков теряют маркеры при переводе

### Новая архитектура (без маскирования)

```
chunk → translate() → editor() → post_process() → validate_xml()
```

**Преимущества:**
- Прямой перевод с тэгами (естественно для LLM)
- Editor сравнивает оригинал + перевод для восстановления тэгов
- Post-process валидирует XML через `xc.rem_tags()`
- Удаление 600+ строк кода маскирования

---

## 🧩 Components

### 1. `src/fb2_handler.py:prepare_chunks()`

**Изменение:** Отключить `mask_xml()`

```python
# Сейчас:
masked_chunk = mask_xml(chunk_text)
chunks.append(masked_chunk)  # MaskedXML object

# Будет:
chunks.append(chunk_text)  # Plain string
```

### 2. `src/prompts.json`

**Изменение:** Упростить промпты, удалить инструкции про маркеры

**editor (текущий):** 25+ строк инструкций про IDENTIFIERS  
**editor (новый):** 5-7 строк, фокус на сравнении оригинал+перевод

```json
{
  "editor": {
    "system": "Ты профессиональный редактор-переводчик. Исправь стиль и грамматику, сохранив структуру XML оригинала.",
    "user_xml": "ОРИГИНАЛ ({source_lang}):\n{source_text}\n\nПЕРЕВОД ({target_lang}):\n{translation_1}\n\nЗАДАЧА:\n1. Исправь грамматику и стиль\n2. Восстанови тэги FB2 в тех же позициях, что в оригинале\n3. Верни ТОЛЬКО исправленный перевод с тэгами"
  }
}
```

### 3. `src/utils.py:one_chunk_editor()`

**Изменение:** Передать `source_text` для сравнения

```python
# Сейчас:
def one_chunk_editor(source_lang, source_text, style, lang, country, role, **kwargs)

# Будет:
def one_chunk_editor(source_lang, source_text, translation_1, style, lang, country, role, **kwargs)
# → передаёт в промпт оба текста для сравнения
```

### 4. `app.py:process_chunk_recursive()`

**Изменение:** Добавить `post_process()` после `translate()`

```python
# Сейчас:
final_translation, outline = translate(...)
validate_mask_integrity(chunk.tag_map, final_translation)
repair_markers(final_translation)

# Будет:
final_translation, outline = translate(...)
final_translation = post_process_xml(chunk.text, final_translation)
```

### 5. `app.py:post_process_xml()` (новая функция)

**Задача:** Валидация + восстановление XML

```python
def post_process_xml(source_text, translated_text):
    # 1. XML валидация через xc.rem_tags()
    cleaned = xc.rem_tags(translated_text)
    
    # 2. Подсчёт тэгов (source vs translated)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    
    # 3. Если расхождение > 10% → LLM repair
    if tag_difference(source_tags, translated_tags) > 0.1:
        return llm_repair_xml(source_text, cleaned)
    
    return cleaned
```

---

## 📊 Data Flow

### Шаг 1: Chunking (без маскирования)

```
<section>
  <p>Text 1</p>
  <p>Text 2</p>
</section>
↓
chunk.text = "<p>Text 1</p><p>Text 2</p>"  # ← Без маркеров
```

### Шаг 2: Translate (5 шагов)

```
Step 1: initial_translation("<p>Text 1</p>")
        → "<p>Текст 1</p>" (может потерять тэг)

Step 2: referat("<p>Текст 1</p>")
        → outline (без тэгов)

Step 3: reflect(original + translation_1)
        → "Тэг <p> потерян"

Step 4: improve(original + translation_1 + reflection)
        → "<p>Текст 1</p>" (восстановлен)

Step 5: editor(original + translation_2)
        → "<p>Текст 1</p>" (финальная проверка)
```

### Шаг 3: Post-process

```
xc.rem_tags("<p>Текст 1</p>")
→ Валидация структуры FB2
→ Исправление unclosed tags
→ "<p>Текст 1</p>" (валидный XML)
```

---

## 🧪 Testing Strategy

### Тестовые файлы

| Файл | Размер | Цель |
|------|--------|------|
| `books/ExampleBook.fb2` | 2.1 KB | Быстрый тест (~50 слов) |
| `books/Cargo.fb2` | 82 KB | Полный тест (главы, тэги) |

### Метрики успеха

| Метрика | Сейчас (с маскированием) | Цель (без маскирования) |
|---------|-------------------------|-------------------------|
| Потеря тэгов | 100% чанков | < 5% чанков |
| Валидация FB2 | 60-70% passes | > 95% passes |
| Код (строки) | 651 доп. строк | -400 строк (удаление) |
| Токены | +20% на маркеры | 0% оверхеда |

### Тест-кейсы

1. **Простой чанк** — 1-2 тэга `<p>`
2. **Сложный чанк** — 50-100 тэгов (вложенные `<section>`, `<title>`, `<p>`, `<strong>`)
3. **Пограничный** — тэги в начале/конце чанка
4. **Критичный** — 30% тэгов потеряно при переводе (проверка LLM repair)

---

## 📋 Migration Plan

### Этап 1: Отключение маскирования
- [ ] `fb2_handler.py`: убрать `mask_xml()`
- [ ] `app.py`: убрать `validate_mask_integrity()`, `repair_markers()`
- [ ] Тест на ExampleBook.fb2

### Этап 2: Упрощение промптов
- [ ] `prompts.json`: удалить инструкции про маркеры
- [ ] `editor`: добавить сравнение оригинал+перевод
- [ ] Тест на ExampleBook.fb2

### Этап 3: Post-process
- [ ] `app.py`: добавить `post_process_xml()`
- [ ] `xmlcheck.py`: добавить `count_tags()` helper
- [ ] Тест на Cargo.fb2

### Этап 4: Очистка кода
- [ ] Удалить `mask_xml()`, `unmask_xml()`, `repair_markers()`
- [ ] Удалить `validation_markers` из функций
- [ ] Финальный тест

---

## ⚠️ Risks

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| LLM игнорирует тэги | Средняя | Усиленный промпт editor + post-process |
| xc.rem_tags() слишком агрессивен | Низкая | Тестирование на Cargo.fb2 |
| Увеличение времени перевода | Низкая | Удаление masking/unmasking компенсирует |

---

## ✅ Approval

**Design approved by Nick:** 2026-03-27

**Next step:** Invoke `writing-plans` skill для детального плана реализации.
