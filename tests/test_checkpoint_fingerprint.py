"""A checkpoint may only be resumed against the chunk list it was written for.

Translation progress is stored as "chunk N of the list". Until fingerprinting
existed, the only guard was that the checkpoint named the same book path, so
any change to chunking — a new max_chunk_size, or a cleanup pass that alters
the text before it is split — re-sliced the book and the saved chunks were
spliced onto boundaries they never belonged to. No error was raised; the book
simply came out with passages duplicated and others missing.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402

from src.checkpoint_manager import (  # noqa: E402
    CHECKPOINT_VERSION,
    CheckpointManager,
    compute_fingerprint,
)

CHUNKS = ["First chunk of the book.", "Second chunk.", "Third and last chunk."]
PARAMS = {"max_chunk_size": 6000, "source_lang": "english", "target_lang": "russian"}


def _save(mgr, fingerprint, last_chunk=1):
    mgr.save(
        chunk_id=last_chunk, section_idx=0, chunk_idx=last_chunk,
        stats={"successful": last_chunk + 1, "failed": 0},
        total_source_len=10, total_target_len=12,
        synopsis_history={}, book_path="/books/x.epub",
        start_time_iso="2026-01-01T00:00:00",
        extra={"translated_parts": ["a", "b"]},
        fingerprint=fingerprint,
    )


# --- the digest itself --------------------------------------------------

def test_same_chunks_and_params_give_the_same_digest():
    assert compute_fingerprint(CHUNKS, **PARAMS) == compute_fingerprint(CHUNKS, **PARAMS)


def test_keyword_order_does_not_matter():
    a = compute_fingerprint(CHUNKS, source_lang="english", target_lang="russian")
    b = compute_fingerprint(CHUNKS, target_lang="russian", source_lang="english")
    assert a == b


def test_changed_chunk_text_changes_the_digest():
    edited = list(CHUNKS)
    edited[1] = "Second chunk, cleaned."
    assert compute_fingerprint(edited, **PARAMS) != compute_fingerprint(CHUNKS, **PARAMS)


def test_different_chunk_boundaries_change_the_digest():
    """The exact failure mode: same text, different slicing."""
    merged = ["".join(CHUNKS)]
    assert compute_fingerprint(merged, **PARAMS) != compute_fingerprint(CHUNKS, **PARAMS)


def test_reordered_chunks_change_the_digest():
    assert compute_fingerprint(CHUNKS[::-1], **PARAMS) != compute_fingerprint(CHUNKS, **PARAMS)


def test_chunk_count_is_part_of_the_digest():
    """Concatenation must not collide with the list it was built from."""
    assert compute_fingerprint(["ab"]) != compute_fingerprint(["a", "b"])


def test_changed_target_language_changes_the_digest():
    other = dict(PARAMS, target_lang="german")
    assert compute_fingerprint(CHUNKS, **other) != compute_fingerprint(CHUNKS, **PARAMS)


def test_accepts_a_generator():
    assert compute_fingerprint(c for c in CHUNKS) == compute_fingerprint(CHUNKS)


def test_survives_lone_surrogates():
    """Broken EPUBs yield lone surrogates; hashing must not be what crashes."""
    assert compute_fingerprint(["text \ud800 more"])


# --- save/load round trip -----------------------------------------------

def test_matching_fingerprint_resumes(tmp_path):
    mgr = CheckpointManager(str(tmp_path / "c.json"))
    fp = compute_fingerprint(CHUNKS, **PARAMS)
    _save(mgr, fp)

    loaded = mgr.load(expected_fingerprint=fp)
    assert loaded is not None
    assert loaded["last_chunk"] == 1
    assert loaded["version"] == CHECKPOINT_VERSION
    assert mgr.exists(), "a resumable checkpoint must survive being read"


def test_mismatched_fingerprint_is_discarded(tmp_path):
    mgr = CheckpointManager(str(tmp_path / "c.json"))
    _save(mgr, compute_fingerprint(CHUNKS, **PARAMS))

    resliced = compute_fingerprint(["".join(CHUNKS)], **PARAMS)
    assert mgr.load(expected_fingerprint=resliced) is None
    assert not mgr.exists(), (
        "a checkpoint that cannot be resumed must be removed, not left to be "
        "re-read and re-rejected on every subsequent run"
    )


def test_pre_fingerprint_checkpoint_is_discarded(tmp_path):
    """Version 1 files carry no fingerprint, so they can never be proven safe."""
    path = tmp_path / "c.json"
    path.write_text(json.dumps({
        "version": 1, "book_path": "/books/x.epub", "last_chunk": 1,
        "extra": {"translated_parts": ["a", "b"]},
    }), encoding="utf-8")

    mgr = CheckpointManager(str(path))
    assert mgr.load(expected_fingerprint=compute_fingerprint(CHUNKS, **PARAMS)) is None
    assert not mgr.exists()


def test_load_without_expectation_stays_permissive(tmp_path):
    """Callers that pass no fingerprint keep the old behaviour."""
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"version": 1, "last_chunk": 3}), encoding="utf-8")
    assert CheckpointManager(str(path)).load()["last_chunk"] == 3


def test_missing_file_returns_none(tmp_path):
    assert CheckpointManager(str(tmp_path / "nope.json")).load(expected_fingerprint="x") is None


def test_corrupt_file_still_backed_up(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{not json", encoding="utf-8")
    mgr = CheckpointManager(str(path))
    assert mgr.load(expected_fingerprint="x") is None
    assert os.path.exists(str(path) + ".corrupt")


def test_mismatch_is_logged(tmp_path, caplog):
    import logging
    mgr = CheckpointManager(str(tmp_path / "c.json"))
    _save(mgr, compute_fingerprint(CHUNKS, **PARAMS))
    with caplog.at_level(logging.WARNING, logger="src.checkpoint_manager"):
        mgr.load(expected_fingerprint="something-else")
    assert any("cannot be resumed" in r.getMessage() for r in caplog.records)


# --- both pipelines must use it -----------------------------------------

@pytest.mark.parametrize("module_path,func_name", [
    ("src/calibre_pipeline.py", "translate_chunks"),
    ("app.py", "main"),
])
def test_both_pipelines_validate_before_resuming(module_path, func_name):
    """The classic and Calibre pipelines keep separate resume code; both are
    equally able to corrupt a book by resuming a stale checkpoint, so both
    must compare the fingerprint."""
    source = open(module_path, encoding="utf-8").read()
    assert "compute_fingerprint" in source, (
        f"{module_path} resumes translation by chunk index without checking "
        f"that the chunk list is unchanged"
    )
