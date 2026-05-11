# Sunny Narrator

**Version:** 1.4  
Программа для перевода книг в форматах FB2/EPUB.  
Система AI-перевода с 5-стадийным контролем качества.

## 🔄 Общий workflow

```mermaid
flowchart LR
    A[1. Скачать репо] --> B[2. Установить Python зависимости]
    B --> C[3. Скачать словари spaCy]
    C --> D[4. Настроить .env файл]
    D --> E[5. Конвертировать книгу в book.fb2]
    E --> F[6. Запустить python app.py → book.dic]
    F --> G[7. Редактировать/проверить/очистить словарь]
    G --> H[8. Запустить перевод]
    H --> I[9. Исправить ошибки формата FB2 в текстовом редакторе]
    I --> J[10. Прочитать и вычитать книгу]
```

**Пошаговый workflow:**
1. **Скачайте репозиторий** - `git clone` проекта
2. **Установите зависимости** - `pip install -r requirements.txt`
3. **Скачайте словари spaCy** - для исходного языка
4. **Настройте** - Создайте `.env` из `.env.example` и заполните ключи API
5. **Подготовьте книгу** - Конвертируйте вашу книгу в формат `book.fb2`
6. **Запустите программу** - `python app.py` - создаёт файл словаря `book.dic`
7. **Отредактируйте словарь** - Просмотрите и очистите `book.dic` (удалите ошибки, добавьте исправления)
8. **Запустите перевод** - Запустите `python app.py` для перевода книги
9. **Исправьте ошибки формата** - В текстовом редакторе: удалите лишние теги, исправьте двойные скобки, исправьте ошибки перевода и т.д.
10. **Прочитайте и вычитайте** - Финальная проверка переведённой книги

---

## 🚀 Быстрый старт

```bash
# Установить зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать с вашими ключами API

# Запустить перевод (рекомендуется JSON режим)
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
JSON_MODE=true    # 🚀 Рекомендуется: структурированный JSON

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

## 🧹 Очистка маркеров Calibre

При конвертации книг через Calibre (`ebook-convert`) служебные маркеры для стилизации могут остаться в выходном файле. Sunny Narrator автоматически удаляет эти маркеры:

- `:::{#calibre_link-* .calibre}:::` — блочные маркеры
- `{#calibre_link-* .calibre*}` — inline маркеры
- `class="calibreX"` — CSS классы
- `id="calibre_link-*"` — ID атрибуты

**Автоматическая очистка применяется:**
- После HTML→Markdown конвертации
- Перед Markdown→FB2/EPUB конвертацией
- После генерации FB2 (для прямых FB2→FB2 конвертаций)

**Подробности:** [docs/CALIBRE_MARKERS_CLEANUP.md](docs/CALIBRE_MARKERS_CLEANUP.md)

---

## 📎 Словарь

Файл словаря (`.dic`) обеспечивает консистентность терминологии:

```dic
# Формат: source = target, category, gender, notes
Alice = Алиса, PERSON, she, Главный персонаж
```

**Формат:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 📖 Перевод по глоссарию (Серия книг)

Создайте единый глоссарий для серии книг, чтобы обеспечить последовательную терминологию во всех томах.

### Построение глоссария серии

```bash
# Базовое использование
python app.py --build-series-dict books/ --series-dict-output series.dic

# С пользовательскими порогами
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --min-count-word 5
```

**Параметры:**
- `--build-series-dict` — Путь к папке с книгами FB2/EPUB/TXT
- `--series-dict-output` — Выходной файл словаря (по умолчанию: `series.dic`)
- `--min-count-ner` — Минимальное количество для NER сущностей (по умолчанию: 5)
- `--min-count-word` — Минимальное количество для(common слов (по умолчанию: 10)

**Workflow:**
1. Найти все файлы книг в папке
2. Извлечь текст из каждой книги
3. Запустить NER для поиска именованных сущностей (PERSON, ORG, LOC, GPE)
4. Агрегировать количество во всех книгах
5. Отфильтровать по пороговым значениям
6. Перевести термины через LLM
7. Сохранить единый `.dic` файл

**Вывод:** JSON-формат словаря с полем `book_origin`, показывающим от какой книги произошёл каждый термин.

---

## 💾 Возобновление после сбоя

Автоматическое сохранение прогресса после каждого chunk:

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

## 🔄 Calibre Pipeline (Новое!)

Принимайте **EPUB/FB2** напрямую — без ручной конвертации.

```bash
# Установить системные зависимости
sudo apt install pandoc calibre
pip install -r requirements.txt

# Перевести EPUB/FB2 напрямую
python app.py --pipeline new --output-format fb2
```

**Пайплайн:** EPUB/FB2 → Calibre → HTML → Markdown → Перевод → HTML → Calibre → FB2/EPUB

**Полное руководство:** [docs/INSTALLATION.md](docs/INSTALLATION.md#-calibre-pipeline-new-feature)

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
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) — JSON mode для всех стадий перевода
| **NER CPU Fallback** | [docs/NER_CPU_FALLBACK_ANALYSIS.md](docs/NER_CPU_FALLBACK_ANALYSIS.md) |
| **Промпты** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 Версии

- **v1.4** — Добавлен общий workflow диаграмма и пошаговые инструкции в README
- **v1.3** — Начальный английский README
- **v1.11** — Checkpoint/resume, fallback для пустого ответа, CPU Docker
- **v1.10** — Упрощение remove_tags, исправление статистики токенов
- **v1.9** — 5-стадийный пайплайн, stage-specific температуры
- **v1.0** — Начальный релиз

---

[English](README.md) | [中文](README_CN.md) | [Português](README_PT.md)
