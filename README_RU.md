# Sunny Narrator

**Версия:** 2.2  
**Переводчик книг с управлением глоссарием** для форматов FB2/TXT/EPUB/DOCX/PDF. Система AI-перевода на двух LLM с 5-стадийным контролем качества.

**Предназначен для:**
- 📚 Перевода серий книг по глоссарию (единая терминология во всех томах)
- 🔨 Создания словарей для переводов книг и серий
- 💻 Локальных GPU (16-24 ГБ VRAM) через llama.cpp, Ollama, LM Studio и т.п. — любой OpenAI-совместимый API (1-2 млн токенов на книгу)
- ☁️ Онлайн-сервисов перевода через API
- 👥 Определение пола персонажа, если он не указан в словаре (записывается в .dic и используется в следующих чанках)
- 📏 Автоматическая калибровка контроля длины чанков после перевода по первым 3 чанкам
- 🈶 Адаптация для CJK-языков (корейский, японский, китайский)
- 🌐 Прямой перевод со словарями с CJK-языков на любой язык

## 🔄 Общий workflow

### Поддерживаемые форматы

| Входной формат | Пайплайн |
|----------------|----------|
| **FB2, TXT** | Классический пайплайн (прямая работа с XML — сохраняет структуру poem/stanza/v) |
| **DOCX, EPUB, PDF** | Calibre-пайплайн (через промежуточный HTMLZ) |

Пайплайн выбирается автоматически по расширению файла — флаг `--pipeline` не нужен.

```mermaid
flowchart LR
    A[1. Скачать репо] --> B[2. Установить зависимости]
    B --> C[3. Настроить .env]
    C --> D[4. Указать книгу в FILE]
    D --> E[5. python app.py → book.dic]
    E --> F[6. Проверить/очистить словарь]
    F --> G[7. python app.py → перевод]
    G --> H[8. Вычитать книгу]
```

**Пошаговый workflow:**
1. **Скачайте репозиторий** — `git clone` проекта
2. **Установите зависимости** — `pip install -e .` (используется `pyproject.toml`); для DOCX/EPUB/PDF дополнительно нужны `pandoc` и `calibre`
3. **Настройте** — создайте `.env` из `env.sample`, заполните ключи API и `SOURCE_LANG`/`TARGET_LANG`
4. **Выберите книгу** — `FILE=path/to/book.fb2` (или `.txt`, `.epub`, `.docx`, `.pdf`)
5. **Создайте словарь** — `python app.py` создаёт `book.dic` рядом с книгой (spaCy-модель исходного языка скачивается автоматически). Для FB2/TXT запуск на этом останавливается для проверки словаря; для DOCX/EPUB/PDF перевод продолжается сразу
6. **Отредактируйте словарь** — проверьте и очистите `book.dic` (удалите ошибки, исправьте переводы, укажите пол)
7. **Переведите** — снова запустите `python app.py`; результат кладётся рядом с исходным файлом, с языковым маркером в имени
8. **Прочитайте и вычитайте** — финальная проверка переведённой книги

---

## 🚀 Быстрый старт

```bash
# Установить зависимости
pip install -e .

# Настроить .env
cp env.sample .env
# Отредактировать .env: ключи API, SOURCE_LANG, TARGET_LANG

# FB2/TXT: первый запуск создаёт словарь, второй переводит
# DOCX/EPUB/PDF: словарь и перевод за один запуск
FILE=books/mybook.fb2 python app.py
```

**Полная документация:** [docs/](docs/)

---

## 📋 Конфигурация

### Базовый .env

```bash
# Настройки API
API_KEY_TRANSLATE=ваш-ключ
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it
JSON_MODE=true    # 🚀 Рекомендуется: структурированный JSON на всех стадиях

API_KEY_PROOFREAD=ваш-ключ
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Mistral

# Книга и языки
FILE=books/mybook.fb2
SOURCE_LANG=english
TARGET_LANG=russian

# Обработка
FAST_TRANS=false    # Быстрый режим (пропуск стадий качества)
DEBUG=off
```

**Все опции:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ Режим FAST_TRANS

**Используйте `FAST_TRANS=true` (или `--fast-mode`) для:**
- ✅ Чернового перевода
- ✅ Технической документации
- ❌ НЕ для финальных публикаций и художественного перевода

**Скорость:** ~2.5x быстрее (2 стадии вместо 5)

**Подробности:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 Словарь

Файл словаря (`*.dic`) обеспечивает единую терминологию:

```dic
# Формат: source = target, category, gender, notes
Alice = Алиса, PERSON, she, Главный персонаж
```

- Создаётся автоматически при первом запуске через NER (именованные сущности + частотные слова), затем переводится LLM.
- **Пол персонажей** (`he`, `she`, `it`, `they`): если в словаре пол не указан, стадия синопсиса определяет его по тексту и записывает в `.dic`; персонажи, которых в словаре нет, добавляются в конец как `имя = перевод, PERSON, пол`. Уже указанный в файле пол никогда не перезаписывается — ручные правки всегда в приоритете.

**Формат:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 🈶 CJK-языки (корейский, японский, китайский)

Книги можно переводить с CJK-языков напрямую на любой язык, со словарём:

- **NER:** `ko_core_news_lg` использует собственную схему меток KLUE (`PS`/`LC`/`OG`) — она распознаётся и приводится к `PERSON`/`LOC`/`ORG`.
- **Частотные слова:** минимальная длина слова — 2 символа вместо 5 (CJK-слово обычно занимает 1-3 символа).
- **Контроль длины:** при переводе на алфавитные языки CJK-текст вырастает в 2-4 раза по символам. Ожидаемое соотношение вычисляется по самой книге — медиана принятых чанков; первые 3 чанка проверяются только на грубые сбои (×0,25 … ×5).

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

---

## 📖 Перевод по глоссарию (серия книг)

Создайте единый глоссарий для серии книг, чтобы терминология совпадала во всех томах.

### Построение глоссария серии

```bash
# Базовое использование
python app.py --build-series-dict books/ --series-dict-output series.dic

# С пользовательскими порогами
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --min-count-word 5
```

**Параметры:**
- `--build-series-dict` — путь к папке с книгами FB2/EPUB/TXT
- `--series-dict-output` — выходной файл словаря (по умолчанию: `series.dic`)
- `--min-count-ner` — минимальное число упоминаний для NER-сущностей (по умолчанию: 2)
- `--min-count-word` — минимальное число упоминаний для частотных слов (по умолчанию: 5)

Словарь для одной книги строится командой `--build-dict path/to/book`.

**Workflow:**
1. Найти все файлы книг в папке
2. Извлечь текст из каждой книги
3. Запустить NER для поиска именованных сущностей (PERSON, ORG, LOC, GPE, EVENT, FAC, PRODUCT)
4. Сложить количества по всем книгам
5. Отфильтровать по порогам
6. Перевести термины через LLM
7. Сохранить единый `.dic` файл

**Результат:** обычный `.dic` файл (`source = target, category, gender, notes`).

---

## 💾 Возобновление после сбоя

Прогресс автоматически сохраняется после каждого чанка:

```bash
# Прервано на 50%
python app.py  # Ctrl+C

# Автоматическое возобновление
python app.py  # ✓ Продолжено с чанка 51/100
```

Для DOCX/EPUB/PDF флаг `--fresh` игнорирует чекпоинт и начинает перевод заново.

**Подробности:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**GPU (NVIDIA):**
```bash
docker-compose up -d
```

**Только CPU:**
```bash
docker-compose -f docker-compose.cpu.yml up -d
```

**Руководства:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md), [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

---

## 🔄 Calibre-пайплайн (DOCX/EPUB/PDF)

Принимает **DOCX/EPUB/PDF** напрямую — без ручной конвертации.
Пайплайн выбирается автоматически для файлов с расширением `.docx`, `.epub` или `.pdf`.

```bash
# Установить системные зависимости
sudo apt install pandoc calibre
pip install -e .

# Перевести DOCX/EPUB/PDF (автоопределение по расширению)
FILE=books/mybook.epub python app.py --output-format epub
```

**Пайплайн:** DOCX/EPUB/PDF → Calibre → HTML → Markdown → Перевод → HTML → Calibre → DOCX/EPUB/PDF

Служебная разметка Calibre (якоря `calibre_link-*`, классы `.calibre`) удаляется автоматически, а оглавление строится заново по переведённым заголовкам.

> ⚠️ **FB2 не поддерживается Calibre-пайплайном.** У FB2 богатая структура
> (poem/stanza/v), которую промежуточный HTMLZ сплющивает в обычные абзацы —
> потеря качества необратима. Для FB2 используется **классический пайплайн**
> (по умолчанию для `.fb2` и `.txt`): он работает с XML напрямую и сохраняет
> всю структуру книги.

**Полное руководство:** [docs/INSTALLATION.md](docs/INSTALLATION.md#-calibre-pipeline-auto-detected)

---

## 📜 Логирование

В консольном логе видны все шаги перевода: проверки длины с откалиброванным соотношением, запись пола в словарь, найденные в чанке словарные термины, чекпоинты.

![Консольный лог перевода с корейского на русский](logging.png)

- `DEBUG=on` — подробный лог (проверки длины, сопоставление словаря, синопсис)
- `DEBUG_HTTP=on` — дополнительно сырые HTTP-трассы LLM-клиентов
- `LLM_LOGGING=true` — каждый вызов LLM (промпты, ответ, токены, время) в виде JSON-строк в `logs/llm_calls_YYYY-MM-DD.log` (каталог: `LLM_LOGGING_DIR`)

**Подробности:** [docs/LOGGING.md](docs/LOGGING.md)

---

## 📚 Документация

| Тема | Файл |
|------|------|
| **Установка** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Конфигурация** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Режим FAST_TRANS** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Стадии перевода** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Температуры** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Rechunking** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Формат словаря** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Возобновление после сбоя** | [docs/RESUME.md](docs/RESUME.md) |
| **Логирование** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker (CPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker (GPU)** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON-режим** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **Промпты** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 Версии

- **v2.2** — Определение пола персонажей с записью в словарь; калибровка контроля длины перевода по книге; адаптация для CJK (корейский, японский, китайский) и прямой перевод с CJK на любой язык
- **v2.1** — Автоопределение пайплайна по формату (.docx/.epub/.pdf → Calibre; .fb2/.txt → классический); удалён флаг `--pipeline`
- **v2.0** — Переход с requirements.txt на pyproject.toml; PyTorch CUDA 12.1 + cuPy
- **v1.4** — Добавлены общая workflow-диаграмма и пошаговые инструкции в README
- **v1.3** — Начальный английский README
- **v1.11** — Checkpoint/resume, fallback для пустого ответа, CPU Docker
- **v1.10** — Упрощение remove_tags, исправление статистики токенов
- **v1.9** — 5-стадийный пайплайн, температуры по стадиям
- **v1.0** — Начальный релиз

---

[English](README.md) | [中文](README_CN.md) | [Português](README_PT.md)
