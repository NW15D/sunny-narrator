# Translation Stages — Prompts and Outputs

## 📋 5-Stage Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: INITIAL (Translate LLM)                               │
│ Input: source_text, outline_text, vocab_dict                    │
│ Output: initial_translation (draft)                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: REFLECTION (Proofread LLM)                            │
│ Input: source_text, initial_translation                         │
│ Output: suggestions (feedback list)                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: IMPROVE (Proofread LLM)                               │
│ Input: initial_translation, suggestions, vocab_dict             │
│ Output: improved_translation (corrected translation)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: FINAL_EDIT (Proofread LLM)                            │
│ Input: improved_translation, source_text, vocab_dict            │
│ Output: final_translation                                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 5: SYNOPSIS (Translate LLM)                                │
│ Input: final_translation                                        │
│ Output: synopsis (context for next chunk)                       │
└─────────────────────────────────────────────────────────────────┘
```

### 🧩 JSON Mode Output Formats

When `JSON_MODE=true` is set, all 4 translation stages use structured JSON output instead of XML tags.

| Stage | JSON Output Format |
|-------|-------------------|
| **INITIAL** | `{"translation": "translated text with <p> tags..."}` |
| **REFLECTION** | `{"suggestions": ["feedback 1", "feedback 2"]}` |
| **IMPROVE** | `{"translation": "corrected translation"}` |
| **FINAL_EDIT** | `{"translation": "final translation"}` |

> ⚠️ Stage 5 (SYNOPSIS) always uses plain text — no JSON mode for synopsis.

See [JSON Mode Analysis](../JSON_MODE_ANALYSIS.md) for complete input/output specifications.

---

## 🎯 Stage 1: INITIAL (Initial Translation)

**LLM:** Translate (Hunyuan/Gemma/etc.)  
**Temperature:** 0.01 (consistency)  
**Output:** Draft translation

### Prompt (prompts.json: initial_translation)

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

### Output
```xml
<ttext>
<p>In the 14th District Court of Texas, Judge John C. Wright is presiding.</p>
<p>ROLANDO ORTELLA, court clerk: Please state your name and occupation for the record.</p>
</ttext>
```

---

## 🔍 Stage 2: REFLECTION (Quality Review)

**LLM:** Proofread (Mistral/Qwen/etc.)  
**Temperature:** 0.4 (creativity)  
**Output:** Feedback ONLY (list)

### Prompt (prompts.json: reflection)

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

### Output (FEEDBACK ONLY)
```
1. "State your name" translated as "Name yourself" — better to use "Please introduce yourself" for formal court context.
2. "clerk of the court" — "court clerk" is not quite accurate, better: "court secretary".
3. "presiding" was omitted in translation — add "is presiding" or "is conducting the hearing".
4. Name "John C. Wright" should be consistent with dictionary: "John C. Wright".
5. The polite tone of "please" is not conveyed well enough — add "please" at the end.
```

### ⚠️ Important!

**REFLECTION must return FEEDBACK ONLY**, not:
- ❌ Translation again
- ❌ Process explanations
- ❌ Meta-commentary

If output is not a feedback list, check:
1. Prompt explicitly says "Output ONLY numbered suggestions"
2. max_tokens is sufficient (MAX_TOKENS_PER_CHUNK)
3. LLM is not ignoring the instruction

---

## ✏️ Stage 3: IMPROVE (Apply Feedback)

**LLM:** Proofread (Mistral/Qwen/etc.)  
**Temperature:** 0.4 (flexibility)  
**Output:** Corrected translation

### Prompt (prompts.json: improve)

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

### Output
```xml
<ttext>
<p>In the 14th District Court of Texas, Judge John C. Wright is presiding.</p>
<p>ROLANDO ORTELLA, court secretary: Please introduce yourself for the record.</p>
</ttext>
```

---

## 📝 Stage 4: FINAL_EDIT (Final Proofreading)

**LLM:** Proofread (Mistral/Qwen/etc.)  
**Temperature:** 0.15 (precision)  
**Output:** Final translation

### Prompt (prompts.json: editor)

**System:**
```
You are a professional translator-editor for {target_lang} ({country}). 
Your task is to perform final proofreading of the translation.

Output ONLY the corrected translation, without explanations.
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

TASK: Perform final editing of the translation for {target_lang} readers in {country}.

1. Fix grammar and style of the translation
2. Restore FB2 tags (<p>, <strong>, <em>, etc.) at the same positions as in the original
3. Verify term consistency with dictionary (use vocabulary strictly)
4. Ensure cultural appropriateness for {country}
5. Maintain narrative tone and style of the original

Important: Compare original and translation section by section, restoring lost tags.
Return ONLY the corrected translation.
```

### Output
```xml
<ttext>
<p>In the 14th District Court of Texas, Judge John C. Wright is presiding.</p>
<p>ROLANDO ORTELLA, court secretary: Please introduce yourself for the record.</p>
<p>HENRY SCAR: Scar, Hank... Henry. I'm a mechanic at Allied.</p>
</ttext>
```

---

## 📖 Stage 5: SYNOPSIS (Synopsis)

**LLM:** Proofread (Mistral/Qwen/etc.)  
**Temperature:** 0.15 (precision)  
**Output:** Short synopsis (~80 words)

### Prompt (prompts.json: synopsis)

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

### Output
```
Court hearing in Texas. Court secretary Rolando Ortellia questions witness Henry Scar, a mechanic at Allied Fruit Growers. Prosecutor Jane Berrendt and defense attorney Benjamin Babidge are present.
```

---

## 🐛 Troubleshooting

### Problem: REFLECTION does not return feedback

**Symptoms:**
- Empty result
- Returns translation instead of feedback
- Returns meta-commentary

**Solution:**
1. Check prompt — must explicitly say "Output ONLY numbered suggestions"
2. Check max_tokens — must be MAX_TOKENS_PER_CHUNK
3. Check temperature — 0.4 for creativity

### Problem: IMPROVE ignores feedback

**Symptoms:**
- Translation does not change after the stage
- Feedback is not applied

**Solution:**
1. Check that {reflection} is passed into the prompt
2. Check prompt — "Apply ALL numbered suggestions"
3. Increase max_tokens if needed

### Problem: FINAL_EDIT returns explanations

**Symptoms:**
- LLM adds comments like "I fixed..."
- Output is not a clean translation

**Solution:**
1. Check system prompt — "Output ONLY the corrected translation"
2. Check user prompt — "Return ONLY the corrected translation"
3. Add filtering in remove_tags()

---

## 📊 Summary Table

| Stage | LLM | Temperature | Input | Output | Prompt |
|-------|-----|-------------|-------|--------|--------|
| **1. INITIAL** | Translate | 0.01 | source_text, vocab | initial_translation | initial_translation |
| **2. REFLECTION** | Proofread | 0.4 | source, translation | suggestions (list) | reflection |
| **3. IMPROVE** | Proofread | 0.4 | translation, suggestions | improved_translation | improve |
| **4. FINAL_EDIT** | Proofread | 0.15 | improved_translation, source | final_translation | editor |
| **5. SYNOPSIS** | **Translate** | 0.15 | final_translation | synopsis | synopsis |

---

## Changelog

- **2026-03-29:** Initial documentation of 5-stage pipeline
- **2026-03-29:** Enhanced reflection prompts for suggestions-only output
- **2026-03-29:** Added troubleshooting section
- **2026-04-28:** Added JSON mode documentation

---

## 🧩 JSON Mode

When `JSON_MODE=true`, all stages use structured JSON input/output.

### Activation

```bash
# .env
JSON_MODE=true
```

### Stage 1: INITIAL (JSON Mode)

**Prompt Category:** `initial_translation_json`

**JSON Input:**
```json
{
  "source": "text to translate",
  "source_lang": "en",
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {"term": "translation"},
  "synopsis": "context from previous chunks"
}
```

**JSON Output:**
```json
{"translation": "translated text"}
```

---

### Stage 2: REFLECTION (JSON Mode)

**Prompt Category:** `reflection_json`

**JSON Input:**
```json
{
  "source": "original text",
  "translation": "translation",
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

### Stage 3: IMPROVE (JSON Mode)

**Prompt Category:** `improve_json`

**JSON Input:**
```json
{
  "translation": "current translation",
  "suggestions": ["suggestion 1", "suggestion 2"],
  "target_lang": "ru",
  "country": "RU",
  "vocabulary": {}
}
```

**JSON Output:**
```json
{"translation": "improved translation"}
```

---

### Stage 4: FINAL_EDIT (JSON Mode)

**Prompt Category:** `editor_json`

**JSON Input:**
```json
{
  "translation": "translation after IMPROVE",
  "target_lang": "ru",
  "country": "RU"
}
```

**JSON Output:**
```json
{"translation": "final translation"}
```

---

### References

- [docs/JSON_MODE_ANALYSIS.md](../JSON_MODE_ANALYSIS.md) — full documentation
- [docs/superpowers/specs/2026-04-28-json-llm-response-design.md](../superpowers/specs/2026-04-28-json-llm-response-design.md) — design specification
