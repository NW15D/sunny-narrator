# Sunny Narrator

**Ранняя версия AI-переводчика длинных текстов** (FB2, EPUB, TXT)

![sh.png](sh.png)

**Быстрый старт:** Для быстрого бесплатного перевода используйте [Hunyuan (Tencent)](https://huggingface.co/tencent/HY-MT1.5-7B-GGUF) или [TranslateGemma (Google)](https://huggingface.co/google) — требуется 5-12GB VRAM.

---

## Возможности

- Перевод словаря (имена, термины)
- Вычитка и корректура
- Синопсис для согласованности перевода
- Региональные нюансы
- Сохранение юмора и ненормативной лексики
- Проверка длины и авто-исправление ошибок
- Параллельный перевод и вычитка через 2 API/LLM
- Генерация обложки книги
- Перевод метаданных для FB2 и EPUB
- Поддержка Docker

---

## Требования

1. **Железо:** GPU с CUDA и драйвером NVIDIA (2GB+ VRAM), или Docker
2. **API:** OpenAI-совместимый API (llama.cpp, OpenAI, Claude и др.)
3. **Входные данные:** FB2 или TXT файл (EPUB конвертируется в FB2)
4. **Окружение:** Docker или Python 3.10+

---

## Конфигурация

Создайте файл `.env`:

### Общие настройки

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `FILE` | Путь к файлу | `books/Cargo.fb2` |
| `SOURCE_LANG` | Исходный язык | `english` |
| `TARGET_LANG` | Целевой язык | `russian` |
| `COUNTRY` | Страна для контекста | `Россия` |
| `MAX_LEN_CHUNK` | Размер чанка (токены) | `8192` |
| `FAST_TRANS` | Быстрый режим | `on` |
| `DEBUG` | Подробные логи | `off` |

### API Перевода (Основной)

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `API_KEY_TRANSLATE` | API ключ | `your-key` |
| `API_BASE_TRANSLATE` | URL API | `http://localhost:6155/v1` |
| `MODEL_TRANSLATE` | Модель | `Hunyuan` |
| `TEMP_TRANSLATE` | Температура | `0.01` |
| `TIMEOUT_TRANSLATE` | Таймаут (сек) | `6000` |

### API Вычитки (Вторичный)

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `API_KEY_PROOFREAD` | API ключ | `your-key` |
| `API_BASE_PROOFREAD` | URL API | `http://localhost:6150/v1` |
| `MODEL_PROOFREAD` | Модель | `Ministral8b` |
| `TEMP_PROOFREAD` | Температура | `0.01` |

### API Изображений (Обложка)

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `API_KEY_IMAGES` | API ключ | `''` |
| `MODEL_IMAGES` | Модель | `gpt-image-1.5` |

### Продвинутые

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `NER` | Авто-словарь (NER) | `True` |
| `NERMODEL` | spaCy модель | `en_core_web_lg` |

---

## Исходные языки

Поддерживаются spaCy: `en`, `ru`, `zh`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `cs`, `pl`, `uk`, `tr`, `nl`

Целевые языки: Любой 2-буквенный код (зависит от LLM)

---

## Запуск

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```

**Первый запуск:** Тестируйте на файле ≤100 слов.

---

## Исправление сохранения XML-тэгов (2026-03-27)

**Проблема:** Предыдущая реализация использовала маскирование XML-тэгов маркерами `@@@TAG_n@@@`, что приводило к потере 100% маркеров при переводе.

**Решение:** Отказ от маскирования в пользу прямого перевода с тэгами + пост-обработки для восстановления структуры.

### Изменения

| Компонент | До | После |
|-----------|-----|-------|
| **Подход** | Маскирование маркерами | Прямой перевод с XML |
| **Потеря тэгов** | 100% чанков | < 5% (ожидаемо) |
| **Код** | +651 строка | -600 строк |
| **Промпты** | 25+ строк инструкций | 5 строк |
| **Токены** | +20% оверхед | 0% оверхеда |

### Архитектура

**До:**
```
chunk → mask_xml() → translate() → editor() → unmask_xml() → validate()
```

**После:**
```
chunk → translate() → editor() → post_process_xml() → validate_xml()
```

### post_process_xml()

Новая функция для валидации и восстановления XML:

1. **XML валидация** через `xc.rem_tags()` — очистка от артефактов
2. **Подсчёт тэгов** — сравнение оригинала и перевода
3. **LLM repair** — если расхождение > 10%, восстановление через LLM

```python
def post_process_xml(source_text, translated_text):
    cleaned = xc.rem_tags(translated_text)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        cleaned = llm_repair_xml(source_text, cleaned)
    return cleaned
```

### Документация

- **Spec:** `docs/specs/2026-03-27-xml-tag-preservation-design.md`
- **Plan:** `docs/plans/2026-03-27-xml-tag-preservation.md`
- **Changelog:** `docs/CHANGELOG_XML_FIX.md`

### Тестирование

```bash
# Быстрый тест
python3 app.py 2>&1 | tee test_example.log

# Проверка потери тэгов
python3 -c "
import re
with open('books/ExampleBook.fb2', 'r') as f:
    orig = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
with open('books/ExampleBook_translated.fb2', 'r') as f:
    trans = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
print(f'Потеря тэгов: {(orig-trans)/orig*100:.2f}% (цель: < 5%)')
"
```

**Ожидаемый результат:** Потеря тэгов < 5%

---

## Благодарности

- [POC](https://github.com/andrewyng/translation-agent) — автоматизированный FB2 перевод через LLM-агентов
- Qwen_Coder32B — замечательная модель
- Antigravity — awesome

---

## Информация

Сделано для развлечения и домашнего использования. Этот проект может стать реальным продуктом — есть десятки идей для улучшения качества. Коммерческие сервисы существуют (например, www.inotherword.ai), но создание надёжного коммерческого приложения требует Java, Kafka/RabbitMQ, Postgres, Minio, специализированных LLM — 3-6 месяцев и значительных инвестиций.

---

## Другие языки

- [🇬🇧 English](README.md)
- [🇨🇳 Chinese](README_CN.md)
- [🇧🇷 Portuguese](README_PT.md)
