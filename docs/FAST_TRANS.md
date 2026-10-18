# FAST_TRANS — Fast Translation

`FAST_TRANS=true` (or `--fast-mode`) runs only INITIAL, GENDER and SYNOPSIS:
REFLECTION, IMPROVE and FINAL_EDIT — the proofreading — are skipped. Both
pipelines, JSON mode or not. Default: `false`.

| | Standard | FAST_TRANS |
|---|---|---|
| Stages | INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS | INITIAL → GENDER → SYNOPSIS |
| Proofread LLM | every chunk | only the GENDER fix, when a gender error is found |
| Result | the translation | a draft: the dictionary and the genders are applied, nobody reviewed the text |

What the skipped stages cost, from a cloud run of a 206k-character collection
(ProxyAPI, Gemma 4 + Qwen 3.6): the stages FAST_TRANS keeps took about 30 % of
the LLM time and about 20 % of the money; the proofreading took the rest.

The GENDER stage runs in fast mode too: the code finds the sentences where a
dictionary character's verb or adjective has the other gender and sends only
them to the proofread LLM — unless that is another model on the same local
server as the translate LLM, then to the translate LLM (`GENDER_CHECK`,
`GENDER_LLM`, see [CONFIGURATION.md](CONFIGURATION.md)). With only the
translate model loaded set `GENDER_LLM=translate`. Words in two alphabets are
logged in both modes.

Use it for a draft, to judge a model or a language pair quickly, and — the
main use — to grow the dictionary before the real translation (below).

## Dictionary in fast mode

The dictionary grows by the same rules as in the standard mode: the synopsis
stage is kept, and it is the one that reports new names
(`<genders>`) and coined terms (`<terms>`). Both pipelines (FB2/TXT and
DOCX/EPUB/PDF) use the same `record_dictionary_candidates`.

- New entries join the in-memory dictionary at once, so the following chunks
  of the run use them; a resumed run restores them from the checkpoint.
- They are written to the `.dic` only with `DICT_AUTO_SAVE=true` (default
  `false`). A new entry is appended only when the dictionary does not cover it
  yet: an existing entry, its other case or inflected form and a phrase with a
  known term are skipped. Existing lines are not removed and their
  translations are not changed, but an existing entry may get its **empty
  gender filled in** (and an entry without a category or with `TERM` then
  becomes `PERSON`). Review those lines too, not only the appended ones.

**Differences from the standard mode:**
- The synopsis (and its candidates) comes from the first translation, there
  is no proofreading — the same as with `PARALLEL_STAGES=2`.
- A translation shorter than 200 characters gets no synopsis, so no
  candidates.

### Two passes: a fast draft for the dictionary, then the translation

```bash
# 1. Fast pass: collect names and terms into the .dic
FAST_TRANS=true DICT_AUTO_SAVE=true python app.py

# 2. Review and fix the .dic (new lines at the end, filled-in genders)

# 3. Quality pass with the reviewed dictionary, from scratch
FAST_TRANS=false python app.py --fresh
```

`--fresh` matters in step 3: if the fast pass was interrupted, its checkpoint
would otherwise be resumed — the already fast-translated chunks would stay in
the book and the entries found by that pass would come back into the
in-memory dictionary, including the ones you removed. The same works for every
input format: `FAST_TRANS` and `--fast-mode` (same as `FAST_TRANS=true`) apply
to both pipelines.

---

## Related documentation

- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — the stages of a chunk
- [CONFIGURATION.md](CONFIGURATION.md) — all options
