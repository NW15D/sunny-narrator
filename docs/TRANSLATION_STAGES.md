# Translation Stages — What Happens to a Chunk

A book is cut into chunks of about `MAX_LEN_CHUNK` source characters
([RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md)), and every chunk goes through the
same stages in both pipelines (`translate_chunk` in `src/utils.py`). The
prompts and the JSON each stage exchanges: [PROMPTS_GUIDE.md](PROMPTS_GUIDE.md).

## The stages

| # | Stage | LLM | Temperature | Input → output | `FAST_TRANS` |
|---|---|---|---|---|---|
| — | substitution | code | — | the dictionary translations of the chunk's terms put into the source (base form) | yes |
| 1 | INITIAL | translate | `TEMP_INITIAL` | source + glossary + characters + synopsis → draft | yes |
| 2 | REFLECTION | proofread | `TEMP_REFLECTION` | source + draft + glossary + characters → list of fixes | — |
| 3 | IMPROVE | proofread | `TEMP_IMPROVE` | draft + fixes + characters → translation; skipped when no fix is left | — |
| 4 | FINAL_EDIT | proofread | `TEMP_FINAL_EDIT` | translation + characters → final translation | — |
| — | GENDER | code, then `GENDER_LLM` | `TEMP_GENDER` | only the sentences with a gender error → fixed sentences | yes |
| 5 | SYNOPSIS | translate | `TEMP_SYNOPSIS` | source + translation + characters + glossary → context for the next chunk, dictionary candidates | yes |

Then the code checks the length of the translation against the length this
book's chunks usually have; a chunk far off is split in two and translated
again ([RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md)).

### INITIAL

The only stage that writes the translation from the source. It sees the
glossary lines of the chunk (`Alice = Алиса, PERSON`) and the `<characters>`
block with the genders written the way the target language shows them
(`Алиса — она (сказала)`). An answer in the source language is retried once
with a stronger instruction; an empty one is retried once.

### REFLECTION

The proofread model lists only real errors as `find` / `replace` / `reason`
(gender, lost or added meaning, an untranslated common word, grammar). It is
told that the glossary is already checked: asked to check it, it listed every
term as a fix that changes nothing until `max_tokens`. The code drops the fixes
IMPROVE cannot or must not apply (`_keep_applicable_fixes`): `find` not in the
translation or equal to `replace`, a `replace` with a word of the other
alphabet, a fix that removes a dictionary translation (`_drops_term`).

Its `max_tokens` follows the translation it reviews (a loop is cut sooner), and
it keeps a `presence_penalty` of 1.5 (`PRESENCE_PENALTY_REFLECTION`): without it
the list repeats itself.

### IMPROVE

Applies the fixes left, nothing else. With no fix left it is not called: it
could only rewrite a translation nobody found wrong.

### FINAL_EDIT

Polishes the translation without the source: grammar, agreement, flow. Keeps
names, acronyms, tags and Markdown; does not shorten or add.

### GENDER

Runs in both modes. Without an LLM, the spaCy model of the target language
finds sentences where a dictionary character with gender `he`/`she` is the
subject and the verb or adjective has the other gender ("Алиса сказал"); only
those sentences go to the LLM, in one short call per chunk.

- `GENDER_CHECK=fix` (default) | `warn` (log only) | `off`.
- `GENDER_LLM=auto` (the proofread LLM; with `FAST_TRANS` too, unless it is
  another model on the same local server) | `translate` | `proofread`.
- Languages with something to check: Slavic (verb gender), French, Spanish,
  Portuguese, Italian, Catalan, Romanian, Greek (participles, adjectives).
- The stage enforces the dictionary. A character the translation writes in
  the other gender in half of its gendered sentences or more (at least three,
  counted over the accepted chunks) probably has a wrong gender in the `.dic`:
  it is named in the log and in the final report, and the stage keeps
  enforcing the `.dic` - fix the gender there. A failure of the stage keeps
  the translation as it is.

### SYNOPSIS

Writes the context the next chunk gets (empty at the start of every section)
and two blocks of dictionary candidates: `<genders>` (a gender the source
shows for a character without one in the dictionary — accepted when two chunks
agree) and `<terms>` (coined words). They join the in-memory dictionary for the
rest of the run, and the `.dic` file only with `DICT_AUTO_SAVE=true`
([DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md)).

## When something goes wrong

| What happens | What the code does |
|---|---|
| The translation is much longer or shorter than expected | the chunk is split in two and each half is translated again, up to 3 levels and 15 LLM calls per chunk |
| An answer is cut off (`finish_reason='length'`, or a JSON answer that never closes) | the model usually looped on this input: the chunk is split, not retried as it is |
| A stage fails (malformed answer, API error after its retries) | the chunk is split; a chunk that still fails is tried twice more, then counted as failed: EPUB/DOCX/PDF keep its source text, FB2/TXT get a `[TRANSLATION FAILED: chunk N]` paragraph |
| A network or server error | each request is retried 3 times (2, 4 s) |
| The API refuses the request (401, 403, 404) | the run stops at once with the variable to check (exit code 3): no chunk can succeed |
| The GENDER stage fails | the translation is kept as it is |

## Two chunks at once

`PARALLEL_STAGES=2` starts the translation of the next chunk while the
proofread LLM still works on this one (two LLMs on separate GPUs or servers, or
a hosted API; about 1.4–1.5× faster). The next chunk then gets the synopsis
and the new dictionary entries of this chunk's draft, not of its final text.
No effect with `FAST_TRANS`.

## Fast mode

`FAST_TRANS=true` (or `--fast-mode`): INITIAL, GENDER and SYNOPSIS only, about
2.5× faster, a draft. Details: [FAST_TRANS.md](FAST_TRANS.md).
