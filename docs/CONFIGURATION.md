# Configuration Guide — Полный справочник параметров

**Версия:** 1.11  
**Дата:** 2026-03-30

---

## 📋 Обзор

Файл `.env` содержит все параметры конфигурации Sunny Narrator.

**Минимальная конфигурация:**
```bash
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it

SOURCE_LANG=english
TARGET_LANG=russian
```

---

## 🔧 API Настройки

### Primary LLM (Перевод)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `API_KEY_TRANSLATE` | — | API ключ для Primary LLM |
| `API_BASE_TRANSLATE` | `http://localhost:11434/v1` | Base URL API |
| `MODEL_TRANSLATE` | `Mistral` | Модель для перевода |
| `S_PROMT_TRANSLATE` | `false` | `true` для Gemma 2/3 (не поддерживают system prompts) |
| `TEMP_TRANSLATE` | `0.01` | Базовая температура (fallback) |
| `TIMEOUT_TRANSLATE` | `6000` | Таймаут запросов (сек) |
| `DISABLE_JSON_MODE_TRANSLATE` | `true` | Отключить JSON mode (безопаснее для локальных LLM) |

### Secondary LLM (Корректура)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `API_KEY_PROOFREAD` | — | API ключ для Secondary LLM |
| `API_BASE_PROOFREAD` | `https://api.openai.com/v1` | Base URL API |
| `MODEL_PROOFREAD` | `tencent/Hunyuan-MT-7B` | Модель для корректуры |
| `S_PROMT_PROOFREAD` | `false` | `true` для Gemma 2/3 |
| `TEMP_PROOFREAD` | `0.7` | Базовая температура (fallback) |
| `TIMEOUT_PROOFREAD` | `6000` | Таймаут запросов (сек) |
| `DISABLE_JSON_MODE_PROOFREAD` | `true` | Отключить JSON mode |

### Stage-Specific Temperatures

| Параметр | По умолчанию | Стадия | Описание |
|----------|--------------|--------|----------|
| `TEMP_INITIAL` | `TEMP_TRANSLATE` | 1 | Initial translation (консистентность) |
| `TEMP_REFLECTION` | `0.4` | 2 | Quality review (креативный анализ) |
| `TEMP_IMPROVE` | `0.4` | 3 | Apply suggestions (гибкое редактирование) |
| `TEMP_FINAL_EDIT` | `0.15` | 4 | Final proofreading (точность) |
| `TEMP_SYNOPSIS` | `0.15` | 5 | Synopsis generation (точность) |

**Подробнее:** [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md)

---

## 🌍 Языки

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `SOURCE_LANG` | `english` | Язык оригинала |
| `TARGET_LANG` | `russian` | Целевой язык |
| `COUNTRY` | `Россия` | Страна для локализации |

---

## ⚡ Обработка

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `MAX_LEN_CHUNK` | `8192` | Максимальный размер чанка (символы) |
| `LENGTH_CHECK_THRESHOLD` | `20` | Порог rechunking (%) |
| `FAST_TRANS` | `false` | Быстрый режим (пропуск стадий 2-4) |
| `DEBUG` | `off` | Режим отладки |

**Подробнее:** [FAST_TRANS.md](FAST_TRANS.md), [RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md)

---

## 📎 NER (Named Entity Recognition)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `NER` | `true` | Включить NER обработку |
| `NERMODEL` | `en_core_web_lg` | spaCy модель для NER |

**Подробнее:** [NER_GUIDE.md](NER_GUIDE.md), [NER_CPU_FALLBACK_ANALYSIS.md](NER_CPU_FALLBACK_ANALYSIS.md)

---

## 🐳 GPU/CPU

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `GPU` | `true` | Использовать GPU если доступен |
| `SPACY_USE_GPU` | `false` | Принудительно CPU для spaCy |

**Подробнее:** [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md)

---

## 🖼️ Изображения (Обложка)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `API_KEY_IMAGES` | — | API ключ для генерации изображений |
| `API_BASE_IMAGES` | — | Base URL для изображений |
| `MODEL_IMAGES` | `gpt-image-1.5` | Модель для генерации |

---

## 📝 Примеры конфигурации

### Локальный LLM (Ollama)

```bash
API_KEY_TRANSLATE=ollama
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=gemma2:27b
S_PROMT_TRANSLATE=true
DISABLE_JSON_MODE_TRANSLATE=true

API_KEY_PROOFREAD=ollama
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=mistral:7b
S_PROMT_PROOFREAD=false
DISABLE_JSON_MODE_PROOFREAD=true

GPU=false
NER=true
```

### API (OpenAI/Hunyuan)

```bash
API_KEY_TRANSLATE=sk-xxx
API_BASE_TRANSLATE=https://api.openai.com/v1
MODEL_TRANSLATE=gpt-4

API_KEY_PROOFREAD=sk-xxx
API_BASE_PROOFREAD=https://api.openai.com/v1
MODEL_PROOFREAD=gpt-4

GPU=true
NER=true
```

### CPU-only (без GPU)

```bash
GPU=false
SPACY_USE_GPU=false
NER=true

# Остальные параметры по умолчанию
```

---

## 🔍 Отладка

### Включить DEBUG режим

```bash
DEBUG=on
```

**Что логируется:**
- Запросы/ответы LLM
- Время обработки чанков
- Статистика токенов
- NER извлечение
- Vocabulary matching

### Проверка конфигурации

```bash
python3 -c "from src.config import Config; c = Config(); print(f'NER: {c.ner_opt}, GPU: {c.gpu_enabled}')"
```

---

## 📚 Связанная документация

- [INSTALLATION.md](INSTALLATION.md) — Установка
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-стадийный пайплайн
- [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md) — Температуры
- [NER_GUIDE.md](NER_GUIDE.md) — NER обработка
- [DOCKER_CPU_GUIDE.md](DOCKER_CPU_GUIDE.md) — Docker конфигурация

---

**Версия:** 1.11  
**Обновлено:** 2026-03-30
