# Sunny Narrator

**Версия:** 1.11  
Программа для перевода книг в форматах FB2/EPUB.  
Система AI-перевода с 5-стадийным контролем качества.

## 🚀 Быстрый старт

```bash
# Установить зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать с вашими ключами API

# Запустить перевод
python app.py
```

**Полная документация:** [docs/](docs/)

---

## 📋 Конфигурация

### Базовый .env

```bash
# API настройки
API_KEY_TRANSLATE=ваш-ключ
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it

API_KEY_PROOFREAD=ваш-ключ
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Mistral

# Языки
SOURCE_LANG=english
TARGET_LANG=russian

# Обработка
FAST_TRANS=false    # Быстрый режим (пропуск стадий качества)
DEBUG=off
```

**Все опции:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ Режим FAST_TRANS

**Использовать `FAST_TRANS=true` для:**
- ✅ Чернового перевода
- ✅ Технических документов
- ❌ НЕ для финальных публикаций или художественного перевода

**Скорость:** ~2.5x быстрее (2 стадии вместо 5)

**Подробности:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 Словарь

Файл словаря (`.dic`) обеспечивает консистентность терминологии:

```dic
# Формат: source = target, category, gender, notes
Alice = Алиса, PERSON, she, Главный персонаж
```

**Формат:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 💾 Resume после сбоя

Автоматическое сохранение прогресса после каждого чанка:

```bash
# Прервано на 50%
python app.py  # Ctrl+C

# Автоматическое возобновление
python app.py  # ✓ Продолжено с чанка 51/100
```

**Подробности:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**CPU-only (по умолчанию):**
```bash
docker-compose up -d
```

**GPU (NVIDIA):**
```bash
docker-compose -f docker-compose.gpu.yml up -d
```

**Руководство:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)

---

## 📚 Документация

| Тема | Файл |
|------|------|
| **Установка** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Конфигурация** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **FAST_TRANS Mode** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Стадии перевода** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Температуры** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Rechunking** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Формат словаря** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Resume после сбоя** | [docs/RESUME.md](docs/RESUME.md) |
| **Docker (CPU/GPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **NER CPU Fallback** | [docs/NER_CPU_FALLBACK_ANALYSIS.md](docs/NER_CPU_FALLBACK_ANALYSIS.md) |
| **Промпты** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 Версии

- **v1.11** — Checkpoint/resume, fallback для пустого ответа, CPU Docker
- **v1.10** — Упрощение remove_tags, исправление статистики токенов
- **v1.9** — 5-стадийный пайплайн, stage-specific температуры
- **v1.0** — Начальный релиз

---

[English](README.md) | [中文](README_CN.md) | [Português](README_PT.md)
