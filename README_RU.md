# Sunny Narrator

[English](README.md) | **Русский** | [中文](README_CN.md) | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — перевод книг EPUB, PDF, TXT, FB2 и DOCX на многие языки" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Версия:** 2.9.4  
**AI-переводчик книг с глоссарием (AI book translator)** для FB2/TXT/EPUB/DOCX/PDF — переводчик художественной литературы на базе LLM с двумя независимыми LLM и 5-стадийным контролем качества.

🖥️ **Консольная утилита (CLI)** — без графического интерфейса, нужен базовый опыт работы с командной строкой.

**Почему стоит попробовать:**
- 📚 **Перевод по глоссарию** — словарь `.dic` держит терминологию единой во всей книге и во всей серии
- 🔨 **Развитая работа со словарём** — словарь можно проверить по книге (`dict review`, `dict clean`), он проверяется перед каждым запуском и **сам пытается исправить категорию и пол** каждой записи по самой книге (`DICT_AUTOFIX`)
- 🔁 **Две LLM, 5 стадий** — одна LLM переводит, вторая проверяет и шлифует; каждый чанк проходит INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- ☁️ **[ProxyAPI](https://proxyapi.ru)** / OpenRouter или 💻 **локальные GPU (16–24 ГБ VRAM)** через llama.cpp, Ollama, LM Studio и любой OpenAI-совместимый API (3–4 млн токенов на книгу), или любой облачный API
- 💾 **Устойчивость к сбоям** — чекпоинт после каждого чанка, повторный запуск продолжает с места остановки
- 🎓 Для профессиональных и непрофессиональных переводчиков — черновики и словари в комплекте

## 🚀 Быстрый старт — переведённая книга за два запуска

По умолчанию модели работают в облаке — без видеокарты и локального сервера LLM. Из России удобнее всего [ProxyAPI](https://proxyapi.ru) с оплатой в рублях: `google/gemma-4-26b-a4b-it` (Gemma 4 26B A4B) переводит, `qwen/qwen3.6-35b-a3b` (Qwen 3.6 35B A3B) вычитывает — те же модели, что в эталонной локальной настройке ([каталог и цены](https://proxyapi.ru/models/browse)).

1. **Установка** (Python 3.11+; зависимости берутся из `pyproject.toml`)
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   sudo apt install calibre pandoc     # EPUB/DOCX/PDF; macOS: brew install --cask calibre && brew install pandoc
   ```
2. **Ключ и книга** — получите ключ в [личном кабинете ProxyAPI](https://proxyapi.ru) и пополните баланс на пару сотен рублей. `cp env.cloud.sample .env`, впишите ключ в `API_KEY_TRANSLATE` и `API_KEY_PROOFREAD`, раскомментируйте блок ProxyAPI в конце файла, книгу — в `FILE=books/mybook.epub`, языки — в `SOURCE_LANG` / `TARGET_LANG`.
3. **Первый запуск — словарь.** `python app.py` находит имена и термины книги (spaCy-модель исходного языка скачивается при первом запуске), переводит их, записывает `books/mybook.dic` и останавливается. Просмотрите его: переводы, категории, пол персонажей — в `books/mybook.dictcheck.txt` перечислено то, что книга не решает однозначно.
4. **Второй запуск — книга.** `python app.py` переводит всю книгу; результат появится рядом с исходником, `books/<название>_<язык>.epub`. Наслаждайтесь чтением.

Роман на 450 страниц обойдётся примерно в 135 ₽ (оценка по токенам реального прогона; точный расход — в личном кабинете). В образце рассуждения моделей выключены. Не из России — `env.cloud.sample` как есть работает с [OpenRouter](https://openrouter.ai) (около $1 за такой роман); там он ещё и выбирает провайдеров с полными весами (bf16/fp8), поддерживающих все параметры запроса.

**Путь к идеальной книге — сначала словарь.** Качество перевода больше всего зависит от словаря: каждый чанк берёт из него имена, термины и пол персонажей, поэтому каждая правка в нём видна на каждой странице. Для лучшего результата идите длинным путём:
1. После первого запуска — быстрый черновик, который наращивает словарь: `FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` — стадия синопсиса добавит имена и придуманные термины всей книги и заполнит пустой пол (существующие строки не переписываются); примерно в 2,5 раза быстрее полного перевода.
2. Выверьте словарь: `python app.py dict clean books/mybook.dic` и `python app.py dict review books/mybook.epub --dic books/mybook.dic` (рядом появятся очищенная / проверенная копия и отчёт), затем поправьте руками то, что осталось, — в первую очередь пол.
3. Переведите заново с готовым словарём: `python app.py --fresh`.

**Локальные модели вместо облака:** `env.sample` (llama.cpp, Ollama, LM Studio; 16–24 ГБ видеопамяти); Docker-образы — в следующем разделе. **Нужен только черновик?** `FAST_TRANS=true`.

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
- Отдельные инструменты: `dict clean`, `dict review`, `dict extend`, `dict convert`, `audit`.

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
| **Участие в проекте** | [CONTRIBUTING.md](CONTRIBUTING.md#участие-в-sunny-narrator) |

## 🈶 Исходники на CJK (корейский, японский, китайский)

Прямой перевод с CJK на любой язык поддерживается из коробки: моделям `ja`/`zh` нужен `pip install -e ".[cjk]"` (корейскому ничего дополнительно не нужно); термины ищутся подстрокой, корейские частицы отрезаются при записи словаря, а калибровка длины поглощает рост текста в 2-4 раза. **Все нюансы:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 История изменений

История релизов: [CHANGELOG.md](CHANGELOG.md)
