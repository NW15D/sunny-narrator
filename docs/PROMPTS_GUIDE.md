# Prompts Guide

All prompts live in `src/prompts.json`. The code fills their `{placeholders}`;
a literal brace is written `{{ }}`. `tests/test_prompts.py` checks every
template against the variables its call site passes (a missing variable would
reach the model as a literal `{target_lang}`), that no key is unused, that the
text and JSON variants of a stage carry the same rules, and that each prompt
stays within its length budget.

## Categories

| Category | Keys | Used by | LLM |
|---|---|---|---|
| `initial_translation` | `system`, `user_xml` (FB2), `user_text` (Markdown: EPUB/DOCX/PDF), `user_hunyuan` (only `MODEL_TRANSLATE=Hunyuan`) | INITIAL, text mode | translate |
| `reflection`, `improve`, `editor` | `system`, `user_xml`, `user_text` | REFLECTION, IMPROVE, FINAL_EDIT, text mode | proofread |
| `initial_translation_json`, `reflection_json`, `improve_json`, `editor_json` | `system`, `user_text` | the same stages in JSON mode (the default) | as above |
| `gender_fix` | `system`, `user` | GENDER: only the sentences `gender_check` flagged | `GENDER_LLM` (proofread by default) |
| `synopsis` | `system`, `user`, `dictionary_rules` (appended to `user`) | SYNOPSIS: context for the next chunk, new dictionary candidates | translate |
| `vocabulary` | `user` | translating a new dictionary (`--build-dict`, `dict extend`) | proofread |
| `metadata_translation` | `user` | title, annotation, other metadata | proofread |
| `image_generation` | `generation`, `variation` | the cover (only with `API_KEY_IMAGES`) | images |

`vocabulary` and `metadata_translation` have no system message.

## The pipeline and what each stage sees

```
source chunk ── terms of the dictionary substituted (base form)
  │
  ├─ INITIAL      translate LLM   source + vocabulary + characters + synopsis → translation
  ├─ REFLECTION   proofread LLM   source + translation + vocabulary + characters → fixes
  ├─ IMPROVE      proofread LLM   translation + fixes + characters → translation   (skipped when no fix is left)
  ├─ FINAL_EDIT   proofread LLM   translation + characters → translation
  ├─ GENDER       GENDER_LLM      only flagged sentences + characters → fixed sentences
  └─ SYNOPSIS     translate LLM   source + translation + characters + glossary → synopsis, <genders>, <terms>
```

With `FAST_TRANS=true` only INITIAL, GENDER and SYNOPSIS run.

Agreements between the stages:

- **Before INITIAL** the translations of the dictionary terms found in the chunk
  are substituted into the source in their base form; the prompt asks the model
  to inflect them. Only INITIAL and REFLECTION see the source.
- **REFLECTION** lists only real errors as pairs: the shortest wrong fragment
  copied from the translation, its fix, a reason under ten words. The
  vocabulary is "already checked": the prompt does not ask the model to check
  it — asking made the model list every term as a fix that changes nothing,
  until `max_tokens`. The code keeps the vocabulary instead: a fix that removes
  a dictionary translation, contains a word of the other alphabet or changes
  nothing is dropped before IMPROVE.
- **IMPROVE** applies the fixes left and nothing else; with no fix left it is not
  called at all (it could only rewrite the text).
- **FINAL_EDIT** polishes without the source: it keeps names, acronyms and markup
  and does not shorten or add.
- **GENDER** gets only the sentences where a dictionary character is the
  subject and the verb or adjective has the other gender; a failure keeps the
  translation as it is.
- **SYNOPSIS** writes the context for the next chunk and two blocks of
  dictionary candidates (rules: `synopsis.dictionary_rules`): `<genders>` —
  characters whose gender the source shows, `<terms>` — coined words. See
  [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md).

### Gender of the characters

The gender is not a field of the glossary line but a `<characters>` block in
every stage (in JSON mode the `"characters"` key), one line per character
written the way the target language shows it: `Алиса — она (сказала)`
(`gender_check.characters_lines`). A small model copies the verb form it sees
more reliably than it carries "she" from the end of a glossary line.

## JSON mode

On by default (`JSON_MODE=true`); `JSON_MODE=false` switches to the text
prompts. Input objects, as the code builds them:

| Stage | Input keys | Output |
|---|---|---|
| INITIAL | `source`, `source_lang`, `target_lang`, `country`, `vocabulary`, `characters`, `synopsis` | `{"translation": "…"}` |
| REFLECTION | `source`, `translation`, `source_lang`, `target_lang`, `country`, `vocabulary`, `characters` | `{"fixes": [{"find": "…", "replace": "…", "reason": "…"}]}` |
| IMPROVE | `translation`, `fixes`, `characters` | `{"translation": "…"}` |
| FINAL_EDIT | `translation`, `characters` | `{"translation": "…"}` |

In text mode REFLECTION writes one fix per line, `«wrong» → «right» — reason`,
or exactly `NO CHANGES`.

An answer is parsed as JSON first; a JSON answer that never closes (the
provider cut it off) fails the stage and the chunk is split, as for any
truncated answer. A closed but invalid one is read by a fallback that decodes
its escapes; plain text and `<ttext>` wrappers are accepted too.

## System prompt merging (`S_PROMT_*`)

`S_PROMT_TRANSLATE=true` / `S_PROMT_PROOFREAD=true` send the system prompt and
the user prompt as one user message, for models whose chat template rejects a
system role (Gemma 2 and 3). Gemma 4 and Qwen 3.6, the reference models,
accept a system message: keep `false`.

## Changing a prompt

The prompts are written for small models (the reference ones are
mixture-of-experts models of 26–35B parameters with 3–4B active): a new rule replaces an old one rather than being added on top, and a
change is measured, not judged on one chunk. `app.py eval` translates the same
passages of a book with your models and compares two runs:

```bash
python app.py eval books/MyBook.epub --dic books/MyBook_ru.dic --count 8 --out logs/eval/before.json
python app.py eval books/MyBook.epub --dic books/MyBook_ru.dic --count 8 \
  --prompts my_prompts.json --out logs/eval/after.json --compare logs/eval/before.json
```

`--prompts FILE` takes the prompts of that file over `src/prompts.json` for
this run only; `--no-glossary` and `--no-substitution` switch the glossary off
in the prompts or the substitution before INITIAL.
