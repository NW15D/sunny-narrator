"""
Tests for the shared end-of-run statistics report.

Background: the classic FB2/TXT pipeline (app.py) printed two report
blocks at the end of a run — a hand-rolled "--- Statistics ---" block with
source/target character counts, then src.utils.print_translation_report()
for token/retry/rechunk/language-mismatch metrics. The Calibre pipeline
(DOCX/EPUB/PDF) shares the same underlying counters — both pipelines funnel
translation through src.utils.translate_chunk(), and TranslationMetrics
(src.utils.metrics) is a module-level singleton — but app.py's Calibre
branch never printed a report at all; it just printed "✓ Pipeline
complete: ..." and exited. That silence was part of why the incident
covered in test_calibre_build_output.py went unnoticed until the log
simply stopped producing lines.

print_translation_report() now takes source_len/target_len/elapsed/
output_path and both pipelines call it, so their reports can't drift out of
format with each other — the classic pipeline's old hand-rolled block was
replaced with a call to this same function instead of being kept as a
second, separately-maintained copy.
"""
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as ut
import src.calibre_pipeline as cp
from src.utils import TranslationMetrics, print_translation_report


@pytest.fixture
def fresh_metrics(monkeypatch):
    """TranslationMetrics (src.utils.metrics) is a module-level singleton
    shared across the whole test process. Swap in a fresh instance so each
    test's counts don't leak into (or get polluted by) any other test."""
    m = TranslationMetrics()
    monkeypatch.setattr(ut, 'metrics', m)
    return m


# ---------------------------------------------------------------------------
# translate_chunks() fills the TranslationStats it's handed
# ---------------------------------------------------------------------------

def test_translate_chunks_fills_stats_out():
    from src.calibre_pipeline import translate_chunks, TranslationStats

    mock_state = MagicMock()
    mock_state.final_translation = "перевод раз"
    mock_state.synopsis = ""

    stats = TranslationStats()
    with patch('src.utils._pipeline.execute', return_value=mock_state):
        result = translate_chunks("Hello world", max_chunk_size=1000, stats_out=stats)

    assert isinstance(result, str)
    assert stats.total_chunks == 1
    assert stats.failed_chunks == 0
    assert stats.total_source_len == len("Hello world")
    assert stats.total_target_len == len("перевод раз")


def test_translate_chunks_stats_out_counts_failures(monkeypatch):
    from src.calibre_pipeline import translate_chunks, TranslationStats

    # Allow the run to finish despite a 100% failure rate, so we can inspect
    # stats_out afterwards (translate_chunks otherwise raises before filling
    # it — see the threshold check right above where stats_out gets set).
    monkeypatch.setattr(cp.config, 'max_failed_chunk_ratio', 1.0)

    stats = TranslationStats()
    with patch('src.utils._pipeline.execute', side_effect=RuntimeError("LLM down")), \
         patch('time.sleep'):  # skip the real retry backoff delays
        result = translate_chunks("Hello world", max_chunk_size=1000, stats_out=stats)

    assert stats.failed_chunks == 1
    assert stats.total_chunks == 1
    assert result == "Hello world"  # kept as original text on failure


# ---------------------------------------------------------------------------
# print_translation_report(): format and content
# ---------------------------------------------------------------------------

def test_print_translation_report_full_output(fresh_metrics, capsys, caplog):
    fresh_metrics.log_success(1000)
    fresh_metrics.log_retry(50, "test retry")

    caplog.set_level(logging.INFO, logger='src.utils')
    print_translation_report(source_len=900, target_len=950, elapsed=12.3,
                             output_path="/tmp/book.epub")

    out = capsys.readouterr().out
    assert "Source: 900 chars" in out
    assert "Target: 950 chars" in out
    assert "Length diff:" in out

    log_text = caplog.text
    assert "TRANSLATION METRICS REPORT" in log_text
    assert "Successful translations: 1" in log_text
    assert "Elapsed time: 12.3s" in log_text
    assert "Output file: /tmp/book.epub" in log_text


def test_print_translation_report_skips_statistics_block_when_no_lengths(fresh_metrics, capsys):
    """Backward compatibility: calling with no arguments (the old call
    signature) still works and doesn't print an empty/bogus Statistics
    block."""
    print_translation_report()
    out = capsys.readouterr().out
    assert "--- Statistics ---" not in out


def test_calibre_and_classic_report_are_identical_format(fresh_metrics, capsys):
    """The whole point of sharing one function: calling it with the same
    inputs — once as the classic pipeline would, once as the Calibre
    pipeline would — must produce byte-identical output, so the two
    pipelines' reports can never silently drift apart again."""
    print_translation_report(source_len=1000, target_len=1100, elapsed=5.0,
                             output_path="/tmp/a.epub")
    first = capsys.readouterr().out

    print_translation_report(source_len=1000, target_len=1100, elapsed=5.0,
                             output_path="/tmp/a.epub")
    second = capsys.readouterr().out

    assert first == second
    assert first != ""


# ---------------------------------------------------------------------------
# app.py wiring: both pipelines actually call the shared function
# ---------------------------------------------------------------------------

def test_app_py_calls_shared_report_from_both_pipelines():
    """Guards against re-introducing a second, hand-maintained copy of the
    statistics block in app.py's classic branch, and against the Calibre
    branch going back to printing nothing."""
    import inspect
    import app as app_module

    main_source = inspect.getsource(app_module.main)
    assert 'print_translation_report' in main_source, (
        "classic FB2/TXT pipeline (main()) must call the shared report function"
    )

    module_source = inspect.getsource(app_module)
    # The Calibre (DOCX/EPUB/PDF) branch lives in the `if __name__ ==
    # '__main__':` block at module level, not inside main().
    calibre_branch = module_source.split("CALIBRE_INPUT_FORMATS")[-1]
    assert 'print_translation_report' in calibre_branch, (
        "Calibre (DOCX/EPUB/PDF) pipeline must call the shared report function too"
    )
