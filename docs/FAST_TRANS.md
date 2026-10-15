# FAST_TRANS Mode — Fast Translation

**Version:** 2.9  
**Date:** 2026-10-10

---

> ⚠️ **Compatibility:** JSON mode (`JSON_MODE=true`) works with FAST_TRANS mode.

---

## 📋 Overview

`FAST_TRANS=true` (or `--fast-mode`) skips quality control stages to
accelerate translation. Both pipelines: FB2/TXT and DOCX/EPUB/PDF.

**Configuration:**
```bash
FAST_TRANS=true    # Fast mode (INITIAL, GENDER, SYNOPSIS)
FAST_TRANS=false   # Standard mode, the default
```

The GENDER stage runs in fast mode too: the code finds the sentences where a
dictionary character's verb or adjective has the other gender and sends only
them to the proofread LLM, unless it is another model on the same local
server as the translate LLM (then to the translate LLM) (`GENDER_CHECK`, `GENDER_LLM`, see CONFIGURATION.md). With only
the translate model loaded set `GENDER_LLM=translate`. Words in
two alphabets (`dошло`) are logged in both modes.

---

## ⚡ Mode Comparison

### Standard (5 stages)

```
Stage 1: INITIAL (Translate LLM)    → Translation
Stage 2: REFLECTION (Proofread LLM) → Quality review
Stage 3: IMPROVE (Proofread LLM)    → Apply suggestions
Stage 4: FINAL_EDIT (Proofread LLM) → Proofreading
Stage 5: SYNOPSIS (Translate LLM)   → Summary
```

**Characteristics:**
- **LLM calls:** 5 (2 Translate + 3 Proofread)
- **Speed:** 1.0x (baseline)
- **Quality:** High

---

### FAST_TRANS (2 stages)

```
Stage 1: INITIAL (Translate LLM)    → Translation
Stage 5: SYNOPSIS (Translate LLM)   → Summary
(Stages 2-4 skipped)
```

**Characteristics:**
- **LLM calls:** 2 (2 Translate + 0 Proofread)
- **Speed:** ~2.5x faster
- **Quality:** Medium

---

## 📊 Use Cases

### ✅ USE FAST_TRANS=true

| Scenario | Reason |
|----------|---------|
| **Draft translation** | Sufficient for review |
| **Technical documents** | Fewer stylistic requirements |
| **Internal materials** | Not for publication |
| **Quick check** | To assess translation quality |
| **Large volumes** | When speed is more important than quality |

### ❌ DO NOT USE FAST_TRANS=true

| Scenario | Reason |
|----------|---------|
| **Final publication** | Requires high quality |
| **Literary works** | Nuances of style are important |
| **Children's books** | Precision is required |
| **Poetry** | Rhythm and rhyme are critical |
| **Legal documents** | Accuracy of phrasing is essential |

---

## 📈 Performance

### Translation time (1000 chunks):

| Mode | Time | LLM calls |
|-------|-------|-------------|
| **Standard** | ~100 min | 5000 |
| **FAST_TRANS** | ~40 min | 2000 |

**Savings:** ~60% time

---

### Translation Quality:

| Metric | Standard | FAST_TRANS |
|---------|----------|------------|
| **Grammar** | ✅ Excellent | ✅ Good |
| **Style** | ✅ Excellent | ⚠️ Medium |
| **Terminology** | ✅ Consistent | ⚠️ Variations possible |
| **Nuances** | ✅ Preserved | ⚠️ Partially |

---

## 🔧 Configuration

### Basic setting

```bash
FAST_TRANS=true
```

### Combining with other parameters

```bash
# Fast translation + CPU (hide the GPU from spaCy)
FAST_TRANS=true
CUDA_VISIBLE_DEVICES=

# Fast translation + debug
FAST_TRANS=true
DEBUG=on
```

---

## 📝 Examples

### Example 1: Book draft

```bash
# .env for draft translation
FAST_TRANS=true
DEBUG=off

python app.py
# ~40 min instead of ~100 min
```

### Example 2: Final version

```bash
# .env for final version
FAST_TRANS=false
DEBUG=off

python app.py
# ~100 min, high quality
```

---

## ⚠️ Limitations

### What is lost in FAST_TRANS mode:

1. **REFLECTION (Stage 2)** — No quality analysis
2. **IMPROVE (Stage 3)** — No application of suggestions
3. **FINAL_EDIT (Stage 4)** — No final proofreading

### What is preserved:

1. **INITIAL (Stage 1)** — Base translation
2. **SYNOPSIS (Stage 5)** — Context for subsequent chunks
3. **Vocabulary** — Terminology dictionary, including its growth while translating (see below)
4. **XML structure** — Preservation of tags

---

## 📖 Dictionary in FAST_TRANS mode

The dictionary grows by the same rules as in the standard mode: the synopsis
stage (stage 5) is kept, and it is the one that reports new names
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

### 💡 Two passes: a fast draft for the dictionary, then the quality translation

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

## 📚 Related documentation

- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-stage pipeline
- [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md) — Temperatures
- [CONFIGURATION.md](CONFIGURATION.md) — All parameters

---

**Version:** 2.9  
**Updated:** 2026-10-10
