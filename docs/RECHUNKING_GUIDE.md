# Rechunking Guide — Chunking and Length Validation

**Version:** 2.7  
**Updated:** 2026-10-02

## 📋 Overview

A book is translated in chunks of about `MAX_LEN_CHUNK` source characters.
After all stages of a chunk are done, the translation length is compared with
the length expected for this book. A chunk whose translation is far off —
typically cut at the model's output limit, or with text dropped or invented —
is split in two and each half is translated again (recursively, up to 3
levels).

## ✂️ How books are cut into chunks

**Classic pipeline (FB2/TXT)** — `src/fb2_structure.py`:

- the body is split along its section tree; every section's own text is a
  unit, nested sections are units of their own, nothing outside sections is
  lost;
- a unit is cut into chunks only **between top-level blocks** (paragraphs,
  poems, citations, tables), so every chunk is well-formed XML; an oversized
  poem, citation or epigraph is cut between its stanzas/paragraphs into
  several containers of the same kind;
- a single block bigger than `MAX_LEN_CHUNK` stays whole.

**Calibre pipeline (EPUB/DOCX/PDF)** — `src/markdown_utils.py`: Markdown is cut
between structural blocks (headings, paragraphs, lists, tables, code).

## 🎯 Length check

```
translate chunk (all stages)
  → expected_len = source_len × expected_ratio (learned per book)
  → percent_diff = |target_len − expected_len| / expected_len
  → IF percent_diff > LENGTH_CHECK_THRESHOLD AND source_len ≥ 2000
       split the SOURCE chunk in two, translate each half again
       (max depth 3, at most 15 LLM calls per original chunk)
```

Implementation: `src/utils.py` — `validate_translation_length()`,
`translate_chunk()`; used by both pipelines.

### How a chunk is split

| Chunk | Split |
|-------|-------|
| FB2/TXT, several blocks | between blocks (or stanzas), as close to the middle as possible — both halves stay well-formed |
| FB2/TXT, one huge paragraph | at the sentence end nearest the middle, never inside `<emphasis>`/`<strong>`; the two translations are joined back into **one** paragraph |
| FB2/TXT, one block that cannot be split (no sentence end, a table, ...) | not split; the translation is kept and a warning is logged |
| Calibre (Markdown) | nearest to the middle within the central half, preferring a paragraph break, then the end of a closing tag, a sentence end (incl. CJK `。！？`), a line break, a space between words; never inside a tag or a ``` code block. Only text with none of these is cut in the middle (`split_text_smartly`) |

### Per-book length calibration

Character counts differ between languages: Korean → Russian roughly doubles
the text, Chinese → any alphabetic language grows even more. The expected ratio
is therefore learned from the book itself:

- every accepted chunk of at least 2000 source characters records its
  `target_len / source_len`; the expected ratio is their **median**;
- until **3** chunks are collected (warm-up) only gross failures are rejected:
  a ratio below ×0.25 or ×5 and above; the log shows `calibrating`;
- a chunk kept only because the split depth was exhausted is not recorded;
- calibration restarts for every book (and after resuming from a checkpoint).

Log line: `⚠ SPLIT [FINAL] 6776 → 9000 chars (×1.33, expected ×2.00, 33.6% off)`.

## ⚙️ Configuration

```bash
# .env
MAX_LEN_CHUNK=8192            # chunk size, source characters
LENGTH_CHECK_THRESHOLD=20     # allowed deviation from the expected length, %
```

The minimum chunk size for splitting (2000 characters), the maximum depth (3)
and the LLM call cap per chunk (15) are constants in `src/utils.py`
(`MIN_CHUNK_SIZE`, `MAX_DEPTH`, `MAX_LLM_CALLS_PER_CHUNK`), not `.env` options.

For CJK sources the translation is 2-4× longer in characters: keep
`MAX_LEN_CHUNK` small enough that the translated chunk fits the model's output
token limit, otherwise most chunks end up being split.

## 🐛 Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Many `SPLIT` lines | Lower `MAX_LEN_CHUNK` (the model's output limit is probably hit), or raise `LENGTH_CHECK_THRESHOLD` to 25-30 |
| `cannot be split; keeping its translation` | A single huge block (e.g. a paragraph without sentence ends); check that part of the book by hand |
| Poor quality after splits | Check that the dictionary and synopsis are applied (`DEBUG=on`) |

## 📚 Related documentation

- [CONFIGURATION.md](CONFIGURATION.md) — all options
- [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md) — stage temperatures
- [RESUME.md](RESUME.md) — resume after a crash
