# Resume after a Crash — Checkpoints

**Version:** 2.6  
**Updated:** 2026-09-29

---

## 📋 Overview

Progress is saved after every translated chunk. After a crash, `Ctrl+C`,
`SIGTERM`, a lost connection or a reboot, run the same command again and the
translation continues from the next chunk; nothing already translated is sent
to the LLM again.

```bash
python app.py          # [Chunk 51/100] ... Ctrl+C
python app.py          # Checkpoint found ... Resuming from chunk 52/100
```

---

## 📘 Classic pipeline (FB2/TXT)

Files next to the book (`<book>_<TARGET_LANG>` prefix):

| File | Contents |
|------|----------|
| `…_tmp.fb2` | The translated body written so far — every chunk is appended as soon as it is translated, together with the section tags around it |
| `….checkpoint.json` | Where to continue: last chunk, statistics, synopsis context, the committed size of `…_tmp.fb2`, a fingerprint of the chunk list |

How it stays consistent:

- **One chunk at a time.** A chunk counts as done only after it is in
  `…_tmp.fb2`; the checkpoint records the file size that belongs to finished
  chunks. On resume anything written after that (a chunk interrupted
  mid-write) is cut off, so text is never duplicated.
- **The end of the book** (trailing empty sections, closing tags) is written
  together with the last chunk, so "all chunks done" always means a finished
  file.
- **Signals.** `Ctrl+C` / `SIGTERM` save the checkpoint and exit with code 1.
- **Fingerprint.** The checkpoint is resumed only if the book still splits
  into the same chunks with the same section tree, `MAX_LEN_CHUNK` and
  languages. Otherwise it is ignored (`Checkpoint ignored (...). Starting
  fresh.`) instead of splicing old text onto new boundaries.
- **Missing output.** If `…_tmp.fb2` lost text the checkpoint expects, the
  checkpoint is ignored and the book is translated again.

After a successful run the checkpoint is removed; the final book gets a
timestamp in its name (`Book_russian_1530-2909.fb2` / `.epub`).

---

## 📚 Calibre pipeline (EPUB/DOCX/PDF)

| File | Contents |
|------|----------|
| `<book>.checkpoint.json` | Chunk-level progress, including the translated chunks |
| `<book>.translated.md` + `<book>.meta.json` | The complete translation, written once all chunks are done; a rerun only rebuilds the output file from it (e.g. to try another `--output-format`) |

`--fresh` ignores both and translates the book from scratch.

---

## 📁 Checkpoint structure (classic)

```json
{
  "version": 3,
  "fingerprint": "5f0c…",
  "book_path": "/path/to/book.fb2",
  "last_chunk": 49,
  "last_section_idx": 12,
  "last_chunk_idx": 2,
  "tfile_size": 412345,
  "stats": {"successful": 50, "failed": 0, "total_tokens": 123456, "retry_tokens": 1234},
  "lengths": {"total_source_len": 450000, "total_target_len": 380000},
  "synopsis_history": {"section_12": ["…", "…"]},
  "created_at": "2026-09-29T10:00:00",
  "updated_at": "2026-09-29T11:30:00"
}
```

The checkpoint is written atomically (temporary file + `os.replace`), so a
crash while saving never leaves a half-written JSON.

---

## ⚠️ Notes

- **Upgrading.** Chunk checkpoints from versions before 2.5 are not resumed
  (both pipelines; the classic temporary file changed its format). Finish
  in-progress books with the old version or let them restart. A complete
  Calibre `.translated.md` dump is still reused.
- **One process per book.** Do not run two translations of the same book at
  once.
- **Corrupted checkpoint.** An unreadable JSON is reported
  (`Failed to load checkpoint`) and the translation starts fresh.

---

## 📚 Related documentation

- [CONFIGURATION.md](CONFIGURATION.md) — all options
- [RECHUNKING_GUIDE.md](RECHUNKING_GUIDE.md) — chunking and length checks
- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-stage pipeline
