# Sunny Narrator

[English](README.md) | **Русский** | [中文](README_CN.md) | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — перевод книг EPUB, PDF, TXT, FB2 и DOCX на многие языки" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Версия:** 2.9.3  
**AI-переводчик книг с глоссарием (AI book translator)** для FB2/TXT/EPUB/DOCX/PDF — переводчик художественной литературы на базе LLM с двумя независимыми LLM и 5-стадийным контролем качества.

🖥️ **Консольная утилита (CLI)** — без графического интерфейса, нужен базовый опыт работы с командной строкой.

**Почему стоит попробовать:**
- 📚 **Перевод по глоссарию** — словарь `.dic` держит терминологию единой во всей книге и во всей серии
- 🔨 **Развитая работа со словарём** — словарь можно проверить по книге (`dict review`, `dict clean`), он проверяется перед каждым запуском и **сам пытается исправить категорию и пол** каждой записи по самой книге (`DICT_AUTOFIX`)
- 🔁 **Две LLM, 5 стадий** — одна LLM переводит, вторая проверяет и шлифует; каждый чанк проходит INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- 💻 **Локальные GPU (16-24 ГБ VRAM)** через llama.cpp, Ollama, LM Studio и др. и любой OpenAI-совместимый API (3-4 млн токенов на книгу), или ☁️ любой облачный API
- 💾 **Устойчивость к сбоям** — чекпоинт после каждого чанка, повторный запуск продолжает с места остановки
- 🎓 Для профессиональных и непрофессиональных переводчиков — черновики и словари в комплекте

## 🚀 Быстрый старт — первый перевод за 5 шагов

1. **Клонировать и установить**
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   pip install -e .
   # для DOCX/EPUB/PDF также нужны: sudo apt install pandoc calibre
   ```
2. **Настроить** — `cp env.sample .env`, заполнить `API_KEY_*`, `API_BASE_*`, `MODEL_*`, `SOURCE_LANG`, `TARGET_LANG`, `FILE=books/mybook.fb2`. Формат определяется по расширению (FB2/TXT → classic-пайплайн, DOCX/EPUB/PDF → Calibre-пайплайн).
3. **Построить словарь** — `python app.py` создаёт `books/mybook.dic` и останавливается для проверки.
4. **Отредактировать словарь** — убрать ошибки, поправить переводы и пол (запуск подскажет, в чём он не уверен).
5. **Перевести** — снова `python app.py`; результат появится рядом с исходным файлом, с маркером языка в имени. Затем вычитайте книгу.

**Только CPU или GPU без conda?** Используйте Docker (следующий раздел). **Черновик без стадий проверки?** `FAST_TRANS=true` (примерно в 2,5 раза быстрее).

## 🐳 Docker

Готовые образы (в обоих есть Calibre и pandoc; собираются из `Dockerfile` / `Dockerfile.cpu`, проверяются при каждом пуше в `main`):

```bash
# 1. Скачать образ (GPU или только CPU)
docker pull ghcr.io/nw15d/sunny-narrator:main        # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu    # CPU

# 2. Подготовить папки и конфиг (на хосте)
mkdir -p books output logs
cp env.sample .env
# в .env: ключи API, MODEL_*, SOURCE_LANG/TARGET_LANG, FILE=books/mybook.fb2
cp mybook.fb2 books/

# 3. Запуск — первый проход строит books/mybook.dic, проверьте его и запустите снова для перевода
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# CPU-образ: уберите --gpus all и используйте ...sunny-narrator:main-cpu
```

Вариант с compose (конфиг `.env` читается автоматически): `docker-compose up -d` (GPU) или `docker-compose -f docker-compose.cpu.yml up -d`.

**Руководства:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md), [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

## 📋 Конфигурация

`env.sample` — полный справочник с комментариями: там перечислен каждый параметр системы с описанием и значением по умолчанию, а в конце файла — готовые варианты (два сервера llama.cpp, один Ollama, английский исходник, FB2 → EPUB, быстрый черновик). Основные параметры:

```bash
API_KEY_TRANSLATE=your-api-key-here     # для локального сервера — любая непустая строка
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # LLM перевода (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # LLM вычитки (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru
OUTPUT_FORMAT=fb2                       # fb2|epub для FB2/TXT; epub|docx|pdf для EPUB/DOCX/PDF
```

**Все параметры:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Словарь (основа качества)

- Первый запуск строит `book.dic` автоматически: spaCy-модель исходного языка находит имена; категорию и пол решает сама книга, LLM только переводит.
- Перед каждым переводом словарь **проверяется по книге** (без LLM): уверенные находки исправляют категорию и пол на этот прогон; сам `.dic` молча не меняется — они попадают в `<dic>.reviewed.dic`.
- Записи `PERSON` передают пол в промпт каждой стадии, его соблюдение проверяет стадия GENDER; расы, виды и придуманные слова записывайте как `TERM`.
- Словарь на всю серию: `--build-series-dict`, затем один `series.dic` для всех томов (`DICTIONARY=series.dic`).
- Отдельные инструменты: `dict clean`, `dict review`, `dict convert`, `audit`.

**Команды, правила, работа с серией, нюансы spaCy/CUDA/CJK:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

## ✏️ Промпты

Все промпты стадий лежат в **`src/prompts.json`** — правьте их, чтобы менять стиль, тон и обращение с терминами: правки влияют на качество всего пайплайна (сравнивайте варианты через `python app.py eval`). В Docker файл монтируется из репозитория, так что правки на хосте действуют со следующего запуска.

**Руководство по каждому промпту:** [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md)

## ⚡ FAST_TRANS

`FAST_TRANS=true` (или `--fast-mode`) выполняет только INITIAL + GENDER + SYNOPSIS — примерно в 2,5 раза быстрее, для черновиков и технических текстов, **не** для финальной публикации. Совет: включите вместе с `DICT_AUTO_SAVE=true`, проверьте словарь, затем переведите заново с `--fresh` ради качества. [Подробнее](docs/FAST_TRANS.md)

## 💾 Продолжение, нарезка и логи

- Сбой или Ctrl+C: обычный `python app.py` продолжает с последнего чекпоинта (`--fresh` — начать заново). [Подробнее](docs/RESUME.md)
- Длина чанка калибруется по книге автоматически (медиана соотношения принятых чанков; первые 3 чанка проверяются только на грубые сбои). [Подробнее](docs/RECHUNKING_GUIDE.md)
- Консоль показывает каждый шаг; `DEBUG=on`, `LLM_LOGGING=true` — полные трассы. [Подробнее](docs/LOGGING.md)

## 📖 Перевод серии по глоссарию

```bash
python app.py --build-series-dict books/ --series-dict-output series.dic \
  # опции: --min-count-ner 2  --frequent-words  --min-count-word 5
python app.py --dictionary series.dic   # для каждой книги; запуск не меняет series.dic
```

Пошаговая подготовка словаря серии — в [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#a-dictionary-shared-by-a-series).

## 📚 Документация

| Тема | Файл |
|------|------|
| **Установка** (в т.ч. Calibre-пайплайн) | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Конфигурация** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Работа со словарями** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Стадии перевода** (в т.ч. GENDER) | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Руководство по промптам** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |
| **Режим FAST_TRANS** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Температуры** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Повторная нарезка** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Продолжение после сбоя** | [docs/RESUME.md](docs/RESUME.md) |
| **Логирование** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker (CPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker (GPU)** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON-режим** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **Проверенные языки** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |

## 🈶 Исходники на CJK (корейский, японский, китайский)

Прямой перевод с CJK на любой язык поддерживается из коробки: моделям `ja`/`zh` нужен `pip install -e ".[cjk]"` (корейскому ничего дополнительно не нужно); термины ищутся подстрокой, корейские частицы отрезаются при записи словаря, а калибровка длины поглощает рост текста в 2-4 раза. **Все нюансы:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 История изменений

История релизов: [CHANGELOG.md](CHANGELOG.md)
