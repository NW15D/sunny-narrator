# Sunny Narrator v1.9

Система AI-перевода с 5-стадийным контролем качества.

## 🚀 Быстрый старт

```bash
# Установить зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать .env с вашими ключами API

# Запустить перевод
python app.py
```

## 📋 Конфигурация

### .env файл

```bash
# Primary LLM (Перевод)
MODEL_TRANSLATE=google/gemma-2-27b-it
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
S_PROMT_TRANSLATE=true          # ⚠️ true для Gemma 2/3!
TEMP_TRANSLATE=0.01

# Secondary LLM (Корректура)
MODEL_PROOFREAD=Mistral
API_BASE_PROOFREAD=http://localhost:11434/v1
API_KEY_PROOFREAD=your-key
S_PROMT_PROOFREAD=false
TEMP_PROOFREAD=0.7

# Температуры по стадиям
TEMP_INITIAL=0.01               # Стадия 1: Primary LLM - Перевод
TEMP_REFLECTION=0.4             # Стадия 2: Secondary LLM - Анализ
TEMP_IMPROVE=0.4                # Стадия 3: Secondary LLM - Редактирование
TEMP_FINAL_EDIT=0.15            # Стадия 4: Secondary LLM - Вычитка
TEMP_SYNOPSIS=0.15              # Стадия 5: Secondary LLM - Синопсис

# Языки
SOURCE_LANG=english
TARGET_LANG=russian
COUNTRY=Россия

# Обработка
MAX_LEN_CHUNK=8192
LENGTH_CHECK_THRESHOLD=20
FAST_TRANS=false
DEBUG=off
```

## ⚡ Режим FAST_TRANS

**FAST_TRANS=true** (быстро, 2 стадии):
- Stage 1: INITIAL (Primary LLM)
- Stage 5: SYNOPSIS (Primary LLM)
- ~2.5x быстрее, среднее качество

**FAST_TRANS=false** (стандарт, 5 стадий):
- Полный пайплайн с контролем качества
- Высокое качество

## 📊 5-Стадийный Пайплайн

1. **INITIAL** (Primary, temp=0.01) — Черновик перевода
2. **REFLECTION** (Secondary, temp=0.4) — Анализ замечаний
3. **IMPROVE** (Secondary, temp=0.4) — Исправление по замечаниям
4. **FINAL_EDIT** (Secondary, temp=0.15) — Финальная вычитка
5. **SYNOPSIS** (Secondary, temp=0.15) — Синопсис для контекста

## 📁 Форматы

- **Вход:** FB2, EPUB, TXT
- **Выход:** FB2, EPUB (с сохранением структуры)

## 🎯 Словарь

Автоматическое создание словаря через NER:
```bash
NER=true
NERMODEL=en_core_web_lg
```

Формат словаря (.dic):
```dic
# Format: source = target, category, gender, notes
Alice = Алиса, PERSON, she, 
Wonderland = Страна Чудес, LOC, , 
```

## 🔧 sys_not_promt для Gemma

Gemma 2/3 не поддерживают system prompts:
```bash
S_PROMT_TRANSLATE=true    # Для Gemma
S_PROMT_PROOFREAD=false   # Для Mistral/Llama
```

## 🔧 Управление JSON Mode

### Когда отключать JSON mode:

| Семейство моделей | Значение | Причина |
|-------------------|----------|---------|
| **Gemma 2/3** | `true` (по умолчанию) | Проблемы с JSON mode, используйте plain text |
| **Mistral** | `true` (по умолчанию) | Может возвращать пустые ответы в JSON mode |
| **Llama 3.x** | `true` (по умолчанию) | Локальные версии часто не работают с JSON mode |
| **Hunyuan** | `false` | Поддерживает JSON mode |
| **Qwen** | `false` | Поддерживает JSON mode |
| **OpenAI/GPT** | `false` | Поддерживает JSON mode |

### Конфигурация:

```bash
# По умолчанию: JSON mode отключен (безопаснее для локальных LLM)
DISABLE_JSON_MODE_TRANSLATE=true
DISABLE_JSON_MODE_PROOFREAD=true

# Для API моделей с поддержкой JSON mode:
DISABLE_JSON_MODE_TRANSLATE=false
DISABLE_JSON_MODE_PROOFREAD=false
```

### Обработка пустых ответов

При отключенном JSON mode или пустом ответе LLM:
- **Автоматический retry**: До 2 попыток с логированием ERROR
- **Debug вывод**: Оригинальное содержимое логируется, если `remove_tags()` даёт пустой результат
- **Формат ошибки**: `ERROR - Ответ 0 [stage/role]: X chars → 0 chars after remove_tags`

## 💾 Resume после сбоя

**Автоматическое сохранение прогресса** после каждого чанка в `.checkpoint.json` файл.

### Как работает:

1. **Сохранение:** После перевода каждого чанка создаётся checkpoint с:
   - Статистика (успешные/неуспешные)
   - Длины (source/target)
   - Synopsis history (контекст для следующих чанков)
   - Номер последнего обработанного чанка

2. **Восстановление:** При перезапуске:
   - Находит существующий checkpoint
   - Восстанавливает статистику и контекст
   - Продолжает с места остановки

3. **Очистка:** После успешного завершения checkpoint удаляется

### Пример:

```bash
# Запуск перевода
python app.py

# Прерывание на 50% (Ctrl+C или crash)
# ...

# Перезапуск — автоматический resume
python app.py
# ✓ Checkpoint found: books/ExampleBook_ru_1929-3003.checkpoint.json
# ✓ Resuming from previous session...
# ✓ Resuming from chunk 51/100
```

### Структура checkpoint:

```json
{
  "version": 1,
  "book_path": "/path/to/book.fb2",
  "last_chunk": 49,
  "stats": {
    "successful": 50,
    "failed": 0,
    "total_tokens": 123456
  },
  "lengths": {
    "total_source_len": 450000,
    "total_target_len": 380000
  },
  "synopsis_history": {...},
  "created_at": "2026-03-30T23:00:00Z",
  "updated_at": "2026-03-30T23:30:00Z"
}
```

**Подробнее:** [docs/RESUME.md](docs/RESUME.md)

## 📚 Документация

- [Установка](docs/INSTALLATION.md)
- [Промпты](docs/PROMPTS_GUIDE.md)
- [Температуры](docs/TEMPERATURE_STRATEGY.md)
- [Rechunking](docs/RECHUNKING_GUIDE.md)
- [NER](docs/NER_GUIDE.md)
- [Словарь](docs/DICTIONARY_FORMAT.md)
- [Стадии перевода](docs/TRANSLATION_STAGES.md)
- [Resume после сбоя](docs/RESUME.md) ← **NEW**

## ⚠️ NER и GPU

Если NVRTC ошибки:
```bash
# Использовать CPU для NER
SPACY_USE_GPU=false

# Или удалить cupy
pip uninstall cupy cupy-cuda12x -y
```

## 📝 Версии

- **v1.9** — 5-стадийный пайплайн, stage-specific температуры
- **v1.8** — Rechunking с валидацией длины
- **v1.7** — NER с CPU fallback
- **v1.0** — Initial release

---

[English](README.md) | [中文](README_CN.md) | [Português](README_PT.md)
