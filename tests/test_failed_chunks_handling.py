"""tc-011 (decision e, approved by Nick): failed chunks must be reported
loudly and summed into the stats aggregate — never shipped silently.

When a chunk translation fails (empty result or all retries exhausted),
translate_chunks() keeps the original text in the assembled book so the run
can finish. Requirements under test:
  1. failed_chunks > 0 -> explicit logger.warning naming the failed chunk
     numbers and sizes, recorded in the run statistics aggregate;
  2. failed share > threshold (constant/config, default 0.1) -> logger.error
     and a record in the run report, but NON-blocking: the book is still
     assembled with the original text in those places.

The logic is driven purely by counters and ratios (no source/target language
heuristics), so it is language-agnostic.

TDD: authored before the implementation; the pre-implementation run failed
(no aggregate fields, no threshold error, abort instead of warn) — see the
tc-011 artifact for recorded output.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
from src.calibre_pipeline import translate_chunks, TranslationStats

# Exactly 10 deterministic chunks; no reliance on the real splitter.
CHUNKS = [
    f"Chunk {n} text: the quiet story continues paragraph number {n}."
    for n in range(1, 11)
]


def _mock_translate(failed_numbers, empty_numbers=()):
    """Fake translate_chunk: raises for failed_numbers, returns an empty
    translation for empty_numbers, otherwise returns (translation, synopsis).
    """
    failed_texts = {CHUNKS[n - 1] for n in failed_numbers}
    empty_texts = {CHUNKS[n - 1] for n in empty_numbers}

    def _translate(source_text=None, **kwargs):
        if source_text in empty_texts:
            return "", "synopsis"
        if source_text in failed_texts:
            raise RuntimeError("LLM down (mock)")
        return f"[translated] {source_text}", "synopsis"

    return _translate


def _run(monkeypatch, stats, failed_numbers, empty_numbers=(), ratio=0.0):
    """Drive translate_chunks over the 10 fixed chunks with a mocked
    translate_chunk; key config is pinned for determinism (ratio=0.0 is the
    legacy Config default — the resolver must fall back to 0.1)."""
    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda text, size: list(CHUNKS))
    monkeypatch.setattr(cp.config, 'max_failed_chunk_ratio', ratio)
    monkeypatch.setattr(cp.config, 'parallel_stages', 1)
    monkeypatch.setattr(cp.time, 'sleep', lambda s: None)
    monkeypatch.setattr(cp, 'translate_chunk',
                        _mock_translate(failed_numbers, empty_numbers))
    return translate_chunks('\n\n'.join(CHUNKS), max_chunk_size=1000, stats_out=stats)


def _report_warnings(caplog):
    return [r.getMessage() for r in caplog.records
            if 'failed to translate' in r.getMessage()]


def _errors(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


def test_one_failed_chunk_warns_with_number_and_is_counted(monkeypatch, caplog):
    """(a) 1 of 10 chunks failed -> warning names chunk 3 (number + size),
    stats count it, the book is still assembled with the original text."""
    caplog.set_level(logging.DEBUG)
    stats = TranslationStats()
    result = _run(monkeypatch, stats, failed_numbers={3})

    warnings = _report_warnings(caplog)
    assert warnings, "no failed-chunks warning was logged"
    msg = warnings[0]
    assert f"chunk 3 ({len(CHUNKS[2]):,} chars)" in msg
    assert "1/10" in msg

    assert stats.failed_chunks == 1
    assert stats.failed_chunk_ids == [3]
    assert stats.failed_ratio == pytest.approx(0.1)
    assert stats.max_failed_ratio == pytest.approx(0.1)
    assert stats.threshold_exceeded is False
    assert not any('exceeds threshold' in m for m in _errors(caplog))

    # Book assembled: original kept for chunk 3, translations elsewhere.
    assert CHUNKS[2] in result
    assert result.count('[translated]') == 9


def test_two_of_ten_failed_logs_error_above_threshold_without_blocking(monkeypatch, caplog):
    """(b) 2 of 10 (20% > 10%) -> logger.error + threshold recorded in the
    stats/report, and the run still returns a fully assembled book."""
    caplog.set_level(logging.DEBUG)
    stats = TranslationStats()
    result = _run(monkeypatch, stats, failed_numbers={3, 8})

    errors = [m for m in _errors(caplog) if 'exceeds threshold' in m]
    assert errors, "no threshold logger.error was logged"
    assert "2/10" in errors[0]
    assert "20.0%" in errors[0]

    assert stats.failed_chunks == 2
    assert stats.failed_chunk_ids == [3, 8]
    assert stats.failed_ratio == pytest.approx(0.2)
    assert stats.threshold_exceeded is True

    warnings = _report_warnings(caplog)
    assert warnings and 'chunk 3 (' in warnings[0] and 'chunk 8 (' in warnings[0]

    assert CHUNKS[2] in result and CHUNKS[7] in result
    assert result.count('[translated]') == 8


def test_no_failures_is_quiet(monkeypatch, caplog):
    """(c) 0 failures -> no warning, no error, clean stats."""
    caplog.set_level(logging.DEBUG)
    stats = TranslationStats()
    result = _run(monkeypatch, stats, failed_numbers=set())

    assert not _report_warnings(caplog)
    assert not _errors(caplog)
    assert stats.failed_chunks == 0
    assert stats.failed_chunk_ids == []
    assert stats.failed_ratio == pytest.approx(0.0)
    assert stats.threshold_exceeded is False
    assert result.count('[translated]') == 10


def test_failure_count_is_stable_and_matches_recorded_ids(monkeypatch, caplog):
    """(d) aggregate idempotency: both failure paths (empty output, exhausted
    retries) count once each; repeated runs produce identical counts/ids."""
    caplog.set_level(logging.DEBUG)
    stats = TranslationStats()
    result = _run(monkeypatch, stats, failed_numbers={9}, empty_numbers={5})

    assert stats.failed_chunks == 2 == len(stats.failed_chunk_ids)
    assert stats.failed_chunk_ids == [5, 9]
    assert stats.failed_ratio == pytest.approx(0.2)
    assert stats.threshold_exceeded is True
    assert CHUNKS[4] in result and CHUNKS[8] in result
    assert result.count('[translated]') == 8

    # Second run with fresh stats: counts must neither accumulate nor drift.
    caplog.clear()
    stats2 = TranslationStats()
    result2 = _run(monkeypatch, stats2, failed_numbers={9}, empty_numbers={5})
    assert stats2.failed_chunks == 2
    assert stats2.failed_chunk_ids == [5, 9]
    assert result2.count('[translated]') == 8


def test_threshold_is_configurable(monkeypatch, caplog):
    """Threshold comes from config: a higher configured value suppresses the
    error, while the warning and the stats stay recorded."""
    caplog.set_level(logging.DEBUG)
    stats = TranslationStats()
    _run(monkeypatch, stats, failed_numbers={3, 8}, ratio=0.5)

    assert stats.max_failed_ratio == pytest.approx(0.5)
    assert stats.threshold_exceeded is False
    assert not any('exceeds threshold' in m for m in _errors(caplog))
    assert _report_warnings(caplog)
    assert stats.failed_chunks == 2
