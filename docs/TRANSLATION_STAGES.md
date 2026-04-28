# Translation Stages — Промпты и Выходные Данные

## 📋 Обзор 5-стадийного пайплайна

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: INITIAL (Primary LLM)                                  │
│ Input: source_text, outline_text, vocab_dict                    │
│ Output: initial_translation (черновик)                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: REFLECTION (Secondary LLM)                             │
│ Input: source_text, initial_translation                         │
│ Output: suggestions (замечания, список)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: IMPROVE (Secondary LLM)                                │
│ Input: initial_translation, suggestions, vocab_dict             │
│ Output: improved_translation (исправленный перевод)             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: FINAL_EDIT (Secondary LLM)                             │
│ Input: improved_translation, source_text, vocab_dict            │
│ Output: final_translation (финальный перевод)                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 5: SYNOPSIS (Primary LLM)                                 │
│ Input: final_translation                                        │
│ Output: synopsis (синопсис для следующего чанка)                │
└─────────────────────────────────────────────────────────────────┘
```

### 🧩 JSON Mode Output Formats

When `JSON_MODE=true` is set, all 4 translation stages use structured JSON output instead of XML tags.

| Stage | JSON Output Format |
|-------|-------------------|
| **INITIAL** | `{"translation": "переведенный текст с тегами <p>..."}` |
| **REFLECTION** | `{"suggestions": ["замечание 1", "замечание 2"]}` |
| **IMPROVE** | `{"translation": "исправленный перевод"}` |
| **FINAL_EDIT** | `{"translation": "финальный перевод"}` |

> ⚠️ Stage 5 (SYNOPSIS) always uses plain text — no JSON mode for synopsis.

See [JSON Mode Analysis](../JSON_MODE_ANALYSIS.md) for complete input/output specifications.

---

## 🎯 Stage 1: INITIAL (Первичный перевод)

**LLM:** Primary (Hunyuan/Gemma/etc.)  
**Температура:** 0.01 (консистентность)  
**Выход:** Перевод черновика

### Промпт (prompts.json: initial_translation)

**System:**
```
You are a professional literary translator. Translate text accurately 
while preserving all XML structure. Output ONLY the translated content 
within <ttext>...</ttext> tags. DO NOT output any explanations, 
questions, or meta-commentary. If the input is empty or unclear, 
output <ttext></ttext>.
```

**User (xml):**
```xml
<context>
<synopsis>{outline_text}</synopsis>
<vocabulary>{vocab_dict}</vocabulary>
</context>

<source lang="{source_lang}">
{source_text}
</source>

Translate the text inside <source> to {target_lang}.

Requirements:
1. Preserve all XML tags (<p>, <strong>, <em>, etc.) in their original positions
2. Apply vocabulary terms where applicable
3. Maintain the narrative style and tone
4. Output ONLY the translated text wrapped in <ttext>...</ttext>
```

### Выходные данные
```xml
<ttext>
<p>В 14-м окружном суде штата Техас, судья Джон К. Райт председательствует.</p>
<p>РОЛАНДО ОРЕЛЛЬЯНА, клерк суда: Назовите ваше имя и профессию для протокола, пожалуйста.</p>
</ttext>
```

---

## 🔍 Stage 2: REFLECTION (Анализ качества)

**LLM:** Secondary (Mistral/Qwen/etc.)  
**Температура:** 0.4 (креативность)  
**Выход:** ТОЛЬКО замечания (список)

### Промпт (prompts.json: reflection)

**System:**
```
You are a literary translation quality reviewer for {target_lang} ({country}).

Your task is to review translations for readers in {country}, considering:
- Regional language variations specific to {country}
- Cultural context and local expressions used in {country}
- Natural phrasing that sounds native to {target_lang} speakers in {country}

Review the translation against the source and identify:
1. Accuracy issues (meaning changes, omissions, additions)
2. Terminology inconsistencies (vocabulary usage)
3. Grammar and syntax errors
4. Nuances and natural expression (literary quality)
5. Style deviations from the original tone
6. Cultural appropriateness for {country}

Output ONLY a numbered list of specific improvements. 
DO NOT output the translation itself.
```

**User (xml):**
```xml
<task>
Target language: {target_lang}
Target country: {country}
Task: Review translation and provide improvement suggestions ONLY
</task>

<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

Review the translation for {target_lang} readers in {country}:
1. ACCURACY: Meaning changes or omissions
2. TERMINOLOGY: Check term consistency
3. GRAMMAR: Syntax issues
4. NUANCES: Literary quality improvements
5. STYLE: Tone mismatches
6. CULTURE: Appropriateness for {country}

Output ONLY numbered suggestions. DO NOT output the translation. 
Focus on natural {target_lang} expression appropriate for {country}.
```

### Выходные данные (ТОЛЬКО замечания)
```
1. "State your name" переведено как "Назовите ваше имя" — лучше "Представьтесь, пожалуйста" для формального контекста суда.
2. "clerk of the court" — "клерк суда" не совсем точно, лучше "секретарь суда".
3. "presiding" пропущено в переводе — добавить "председательствует" или "ведёт заседание".
4. Имя "John C. Wright" должно быть согласовано с словарём: "Джон К. Райт".
5. Тон обращения "please" не передан достаточно вежливо — добавить "пожалуйста" в конец.
```

### ⚠️ Важно!

**REFLECTION должен возвращать ТОЛЬКО замечания**, а не:
- ❌ Перевод заново
- ❌ Объяснения процесса
- ❌ Мета-комментарии

Если возвращается не список замечаний — проверить:
1. Промпт явно указывает "Output ONLY numbered suggestions"
2. max_tokens достаточно (MAX_TOKENS_PER_CHUNK)
3. LLM не игнорирует инструкцию

---

## ✏️ Stage 3: IMPROVE (Исправление по замечаниям)

**LLM:** Secondary (Mistral/Qwen/etc.)  
**Температура:** 0.4 (гибкость)  
**Выход:** Исправленный перевод

### Промпт (prompts.json: improve)

**System:**
```
You are a literary translation editor for {target_lang} ({country}).

Your task is to apply reflection suggestions while preserving:
- Original narrative voice and tone
- Obscene/profane language (if present in source)
- Character speech patterns
- Cultural nuances appropriate for {country}
- Regional expressions natural to {target_lang} speakers in {country}

Output the improved translation ONLY.
```

**User (xml):**
```xml
<task>
Target language: {target_lang}
Target country: {country}
Task: Apply suggestions to improve translation
</task>

<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

<suggestions>
{reflection}
</suggestions>

<vocabulary>
{vocab_dict}
</vocabulary>

Apply ALL numbered suggestions to improve the translation for {target_lang} readers in {country}:
1. Fix accuracy issues
2. Apply vocabulary terms correctly
3. Fix grammar
4. Improve literary nuances
5. Maintain style and tone
6. Preserve obscene/profane language if present in source
7. Ensure cultural appropriateness for {country}
8. Use regional expressions natural to {country}

Output the final translation ONLY, wrapped in <ttext>...</ttext>.
```

### Выходные данные
```xml
<ttext>
<p>В 14-м окружном суде штата Техас судья Джон К. Райт ведёт заседание.</p>
<p>РОЛАНДО ОРЕЛЛЬЯНА, секретарь суда: Представьтесь, пожалуйста, для протокола.</p>
</ttext>
```

---

## 📝 Stage 4: FINAL_EDIT (Финальная вычитка)

**LLM:** Secondary (Mistral/Qwen/etc.)  
**Температура:** 0.15 (точность)  
**Выход:** Финальный перевод

### Промпт (prompts.json: editor)

**System:**
```
Ты профессиональный редактор-переводчик для {target_lang} ({country}). 
Твоя задача — провести финальную вычитку перевода.

Выведи ТОЛЬКО исправленный перевод, без объяснений.
```

**User (xml):**
```xml
<task>
Target language: {target_lang}
Target country: {country}
Task: Final proofreading - output corrected translation ONLY
</task>

<original lang="{source_lang}">
{source_text}
</original>

<translation lang="{target_lang}">
{translation}
</translation>

<vocabulary>
{vocab_dict}
</vocabulary>

ЗАДАЧА: Проведи финальную редактуру перевода для {target_lang} читателей в {country}.

1. Исправь грамматику и стиль перевода
2. Восстанови тэги FB2 (<p>, <strong>, <em> и др.) в тех же позициях, что в оригинале
3. Проверь соответствие терминов словарю (используй vocabulary строго)
4. Убедись в культурной уместности для {country}
5. Сохрани повествовательный тон и стиль оригинала

Важно: Сравнивай оригинал и перевод посекционно, восстанавливая потерянные тэги.
Верни ТОЛЬКО исправленный перевод.
```

### Выходные данные
```xml
<ttext>
<p>В 14-м окружном суде штата Техас судья Джон К. Райт ведёт заседание.</p>
<p>РОЛАНДО ОРЕЛЛЬЯНА, секретарь суда: Представьтесь, пожалуйста, для протокола.</p>
<p>ГЕНРИ ШРАМ: Шрам, Хэнк... Генри. Я механик в Allied.</p>
</ttext>
```

---

## 📖 Stage 5: SYNOPSIS (Синопсис)

**LLM:** Secondary (Mistral/Qwen/etc.)  
**Температура:** 0.15 (точность)  
**Выход:** Краткий синопсис (80 слов)

### Промпт (prompts.json: synopsis)

**System:**
```
You are an expert summarizer. Create concise, informative synopses for translation context.
```

**User:**
```xml
<text>
{final_translation}
</text>

Create a synopsis in {target_lang} (max 80 words). Requirements:
- Plain text only (no markdown, no bold/italics)
- No header like 'Synopsis:' or 'Summary:'
- Include character gender if naturally possible
- Output only the synopsis content
```

### Выходные данные
```
Судебное заседание в Техасе. Секретарь суда Роландо Орельяна допрашивает свидетеля Генри Шрама, механика Allied Fruit Growers. Присутствуют прокурор Джейн Беррендт и адвокат защиты Бенджамин Бэббидж.
```

---

## 🐛 Troubleshooting

### Проблема: REFLECTION не возвращает замечания

**Симптомы:**
- Пустой результат
- Возвращает перевод вместо замечаний
- Возвращает мета-комментарии

**Решение:**
1. Проверить промпт — должен явно указывать "Output ONLY numbered suggestions"
2. Проверить max_tokens — должен быть MAX_TOKENS_PER_CHUNK
3. Проверить температуру — 0.4 для креативности

### Проблема: IMPROVE игнорирует замечания

**Симптомы:**
- Перевод не меняется после стадии
- Замечания не применяются

**Решение:**
1. Проверить что {reflection} передаётся в промпт
2. Проверить промпт — "Apply ALL numbered suggestions"
3. Увеличить max_tokens если нужно

### Проблема: FINAL_EDIT возвращает объяснения

**Симптомы:**
- LLM добавляет комментарии типа "Я исправил..."
- Вывод не чистый перевод

**Решение:**
1. Проверить system промпт — "Выведи ТОЛЬКО исправленный перевод"
2. Проверить user промпт — "Верни ТОЛЬКО исправленный перевод"
3. Добавить фильтрацию в remove_tags()

---

## 📊 Сводная таблица

| Стадия | LLM | Температура | Вход | Выход | Промпт |
|--------|-----|-------------|------|-------|--------|
| **1. INITIAL** | Primary | 0.01 | source_text, vocab | initial_translation | initial_translation |
| **2. REFLECTION** | Secondary | 0.4 | source, translation | suggestions (list) | reflection |
| **3. IMPROVE** | Secondary | 0.4 | translation, suggestions | improved_translation | improve |
| **4. FINAL_EDIT** | Secondary | 0.15 | improved_translation, source | final_translation | editor |
| **5. SYNOPSIS** | **Secondary** | 0.15 | final_translation | synopsis | synopsis |

---

## Changelog

- **2026-03-29:** Initial documentation of 5-stage pipeline
- **2026-03-29:** Enhanced reflection prompts for suggestions-only output
- **2026-03-29:** Added troubleshooting section
- **2026-04-28:** Added JSON mode documentation

---

## 🧩 JSON Mode

При `JSON_MODE=true` все стадии используют структурированный JSON ввод/вывод.

### Активация

```bash
# .env
JSON_MODE=true
```

### Стадия 1: INITIAL (JSON Mode)

**Prompt Category:** `initial_translation_json`

**JSON Input:**
```json
{
  "source": "текст для перевода",
  "source_lang": "en",
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {"term": "перевод"},
  "synopsis": "контекст из предыдущих чанков"
}
```

**JSON Output:**
```json
{"translation": "переведённый текст"}
```

---

### Стадия 2: REFLECTION (JSON Mode)

**Prompt Category:** `reflection_json`

**JSON Input:**
```json
{
  "source": "оригинальный текст",
  "translation": "перевод",
  "source_lang": "en",
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {}
}
```

**JSON Output:**
```json
{"suggestions": ["Replace 'X' with 'Y' (reason)"]}
```

---

### Стадия 3: IMPROVE (JSON Mode)

**Prompt Category:** `improve_json`

**JSON Input:**
```json
{
  "translation": "текущий перевод",
  "suggestions": ["suggestion 1", "suggestion 2"],
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {}
}
```

**JSON Output:**
```json
{"translation": "улучшенный перевод"}
```

---

### Стадия 4: FINAL_EDIT (JSON Mode)

**Prompt Category:** `editor_json`

**JSON Input:**
```json
{
  "translation": "перевод после IMPROVE",
  "target_lang": "ru",
  "country": "RU"
}
```

**JSON Output:**
```json
{"translation": "финальный перевод"}
```

---

### Ссылки

- [docs/JSON_MODE_ANALYSIS.md](../JSON_MODE_ANALYSIS.md) — полная документация
- [docs/superpowers/specs/2026-04-28-json-llm-response-design.md](../superpowers/specs/2026-04-28-json-llm-response-design.md) — спецификация дизайна
