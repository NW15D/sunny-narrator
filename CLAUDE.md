# Sunny Narrator — заметки для Claude Code

Glossary-driven AI-переводчик книг (FB2/EPUB/DOCX/PDF/TXT) с dual-LLM
архитектурой (translate-LLM + proofread-LLM) и 5-стадийным контролем
качества перевода. Точка входа: `python app.py` (конфиг берётся из `.env`).

Этот файл — не дублирует README/docs, а помогает быстро найти нужный файл
перед правкой и не наступить на грабли, характерные для этого репозитория.

## Два независимых пайплайна

Выбор пайплайна автоматический, по расширению входного файла
(см. `app.py:1152` и `CALIBRE_INPUT_FORMATS`/`CLASSIC_INPUT_FORMATS`).

| Вход | Пайплайн | Модуль | Особенность |
|---|---|---|---|
| `.fb2`, `.txt` | **Classic** | `app.py` (`TranslationEngine`, `main()`) | Прямая работа с XML/FB2-структурой (сохраняет `poem/stanza/v` и т.д.) |
| `.docx`, `.epub`, `.pdf` | **Calibre** | `src/calibre_pipeline.py` (`run_pipeline`) | Конвертация через Calibre (`ebook-convert`) в HTMLZ → Markdown → перевод чанков → сборка обратно через `ebook-convert` |

Оба пайплайна используют общее ядро перевода в `src/utils.py`
(`TranslationPipeline`, `translate_chunk`) и общий `Config` (`src/config.py`).

**FB2 намеренно не проходит через Calibre-пайплайн** — HTMLZ-конвертация
сплющивает `poem/stanza/v` в `<p>`, поэтому FB2/TXT всегда идут через
classic-пайплайн, даже если когда-нибудь появится `--pipeline` флаг.

## Карта файлов

### Точки входа и конфиг
- `app.py` — classic-пайплайн: CLI-парсинг, `TranslationEngine`, resume/checkpoint для FB2/TXT, сборка путей вывода (`build_resume_paths`), запись FB2/EPUB (`write_to_file`), а также маршрутизация в Calibre-пайплайн при `.docx/.epub/.pdf`.
- `src/config.py` — единый `Config`: читает `.env`, содержит `lang_code_map` (russian→ru и т.п.), `lang_model_map` (spaCy-модели по языку), все LLM-настройки (translate/proofread/images — три независимых API-клиента).

### Calibre-пайплайн (DOCX/EPUB/PDF)
- `src/calibre_pipeline.py` — весь пайплайн: `convert_to_markdown` (EPUB/PDF/DOCX → HTMLZ → Markdown, извлечение картинок и метаданных из OPF), `translate_chunks`/`translate_chunk` (перевод чанков с чекпоинтами), `build_output` (Markdown → HTML → EPUB/DOCX/PDF через Calibre), `run_pipeline` (склеивает все шаги), `validate_output`. Файл **не импортирует output-путь снаружи** — сам решает, куда положить готовый файл (см. «Соглашение об именах выходных файлов» ниже).

### Форматы: парсинг и запись
- `src/fb2_handler.py` — чтение/запись FB2, общие XML-операции для FB2.
- `src/epub_handler.py` — парсинг EPUB → внутреннее FB2-подобное представление (`parse_epub`), используется classic-пайплайном.
- `src/epub_writer.py` — сборка EPUB из переведённой FB2-структуры (`create_epub_from_fb2`), обложка, метаданные.
- `src/epub_repair.py` — валидация и авто-починка EPUB (структура ZIP, OPF-манифест, XHTML).
- `src/fb2_repair.py` — авто-починка XML FB2 (незакрытые теги, лишний контент и т.д.).
- `src/txt_handler.py` — чтение TXT с фолбэком кодировок (utf-8 → charset-normalizer → cp1251 → latin-1).
- `src/xml_utils.py`, `src/xml_post_processor.py`, `src/xmlcheck.py` — общие XML-утилиты, пост-обработка тегов после перевода, XSD-валидация FB2.
- `src/markdown_utils.py` — markdown-утилиты, включая очистку Calibre-маркеров (используется и classic-, и Calibre-пайплайном).
- `src/p_tags_processor.py` — проверка/восстановление `<p>` тегов в переведённых чанках.

### Ядро перевода
- `src/utils.py` — `TranslationPipeline`/`LLMService`: 5 стадий (INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → SYNOPSIS), три независимых LLM-клиента (translate/proofread/images), JSON-режим, парсинг ответов, `translate_chunk()` — общая точка входа для перевода одного чанка (используется обоими пайплайнами).
- `src/synopsis_manager.py` — синопсис как переходящий контекст между чанками (сбрасывается на новой секции).
- `src/checkpoint_manager.py` — атомарное сохранение/восстановление чекпоинтов перевода.
- `src/llm_logger.py` — логирование всех LLM-вызовов в `logs/llm_calls_YYYY-MM-DD.log`.

### Словарь/термины/NER
- `src/vocabulary_manager.py` — управление `.dic` файлами (глоссарий): создание из NER, подбор терминов на чанк (косинусное сходство), форматирование под конкретную модель, консистентность в рамках серии книг.
- `src/character_registry.py` — единый реестр персонажей (пол, алиасы, упоминания), связывает `vocabulary_manager` и `synopsis_manager`.
- `src/ner.py` — извлечение именованных сущностей (spaCy) для построения словаря.

### Тесты и вспомогательное
- `tests/` — ~100 файлов, по одному на фичу/баг (`test_<feature>.py`); `tests/data/` — образцы FB2. `pyproject.toml` игнорирует `tests/test_calibre_cleanup.py` (не тест, а ручной скрипт с реальным `ebook-convert`).
- `scripts/` — вспомогательные скрипты (проверка GPU, очистка Calibre-разметки, докер-тесты).
- `docs/` — подробная документация по темам (конфиг, словари, NER, JSON-режим, докер, resume и т.д.) — смотреть туда за деталями, не дублировать здесь.
- `books/`, `books_test/` — примеры книг для ручного прогона.

## Соглашение об именах выходных файлов (важно при правках путей!)

Оба пайплайна обязаны:
1. класть результат **рядом с исходным файлом** (в его директорию, не в CWD);
2. включать в имя **языковой маркер**, взятый из `config.lang_code_map`
   (например `target_lang=russian` → маркер `ru`), чтобы переводы одной
   книги на разные языки не перезатирали друг друга.

Реализации:
- Classic-пайплайн: `app.py:build_resume_paths()` — `f"{output_dir}/{file_name}_{target_lang}_{timestamp}.{ext}"`.
- Calibre-пайплайн: `src/calibre_pipeline.py:build_output()` — при отсутствии явного `output_path` строит `f"{safe_title}_{lang_marker}.{output_format}"` в директории `input_path` (маркер языка через `config.lang_code_map`, каталог через `os.path.dirname(input_path)`).

Если меняете логику генерации выходного пути — проверяйте оба места, они
не переиспользуют общий хелпер (исторически разъехались).

## Защита неперводимого контента при LLM-переводе

Markdown-чанки в Calibre-пайплайне уходят в LLM как есть — перевод-промпт
не знает про markdown-разметку (только про XML-теги в classic-пайплайне).
Всё, что не является текстом на естественном языке (например
`![alt](images/pic.jpg)`), рискует быть потеряно или испорчено моделью.
Для картинок это решено в `calibre_pipeline.py` через
`_protect_markdown_images()`/`_restore_markdown_images()`: перед разбиением
на чанки все `![...](...)` заменяются на плейсхолдеры, после сборки
перевода — восстанавливаются обратно. Если найдётся другой тип разметки,
который LLM теряет при переводе Calibre-пайплайна, — используйте тот же
приём (placeholder до `translate_chunks`, restore после).

## Запуск тестов в песочнице

В этом окружении нет глобального venv/pytest (`pip install` без
`--break-system-packages` откажет). Создать локальный venv в scratchpad и
поставить зависимости оттуда:

```bash
python3 -m venv /tmp/.../scratchpad/venv
/tmp/.../scratchpad/venv/bin/pip install pytest httpx openai python-dotenv \
  tiktoken langchain-text-splitters pydantic beautifulsoup4 lxml \
  more-itertools EbookLib Pillow pypandoc
API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test \
  /tmp/.../scratchpad/venv/bin/python -m pytest -q
```

`API_KEY_IMAGES` обязателен даже для тестов, не трогающих изображения —
`Config.__init__` инстанцирует все три `openai.OpenAI()` клиента сразу,
и пустой ключ роняет импорт `src.utils` (а с ним — почти любой тест).

Без `spacy` и системного `pandoc`/`ebook-convert` часть тестов падает
(`test_ner_*`, `test_vocab_*`, `test_toc_feature`, кое-что в
`test_atomic_write`, `test_calibre_checkpoint`) — это ограничения
окружения, не регрессии; проверяйте самостоятельно на чистом `git stash`,
если сомневаетесь, что сбой — не от ваших правок.
