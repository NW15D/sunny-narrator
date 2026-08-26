"""
Tests for run_pipeline()'s resume support.

Background: run_pipeline() used to call translate_chunks() without a
checkpoint_file at all, so the whole per-chunk checkpoint mechanism inside
translate_chunks (fully implemented, exercised only by
tests/test_calibre_checkpoint.py) was unreachable from the real Calibre
entry point. Worse, nothing in the pipeline ever wrote the finished
translation to disk before handing it to build_output — so a crash/hang
during Markdown->HTML/EPUB assembly (see tests/test_calibre_build_output.py
for that bug) threw away the entire translation. On a real ~920KB book that
meant 2.4M+ LLM tokens of finished work were lost, and a re-run would have
re-translated the whole book from chunk 0.

The fix gives run_pipeline() two independent recovery layers:
1. checkpoint_file is now passed through to translate_chunks (with
   remove_on_success=False), so a crash *during* translation can resume
   chunk-by-chunk.
2. The finished translation + metadata are dumped to
   <stem>_<lang>.translated.md / .meta.json *before* build_output runs, so a
   crash *during* build_output costs zero additional LLM calls to recover
   from — the next run reads the dump and skips straight to Step 4.

These tests mock convert_to_markdown/translate_chunks/build_output/
validate_output at the src.calibre_pipeline module level: the goal is to
verify run_pipeline's own orchestration (which paths it takes, what it
writes/cleans up, when), not to re-verify translate_chunks' internal
per-chunk checkpointing (already covered by test_calibre_checkpoint.py) or
build_output's pandoc/Calibre handling (covered by
test_calibre_build_output.py).
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.calibre_pipeline as cp
from src.checkpoint_manager import CheckpointManager


def _install_mocks(monkeypatch, *, translate=None, build_output=None, validate_ok=True):
    """Patch the four steps run_pipeline calls out to, so its own resume/
    dump/cleanup logic can be tested without real Calibre/pandoc/LLM calls."""
    monkeypatch.setattr(cp, 'convert_to_markdown',
                        lambda input_path: ("# Chapter\n\nSource text", {"title": "Book"}))
    monkeypatch.setattr(cp, 'extract_dictionary_from_md', lambda *a, **kw: {})
    # run_pipeline now translates title/author/etc. via translate_metadata
    # (see _translate_output_metadata) before dumping/building output. Stub
    # it out here too, same as the other three steps above, so these tests
    # stay hermetic (no real LLM call) — an identity pass-through keeps
    # metadata['title'] == "Book" for the other assertions in this file.
    monkeypatch.setattr(cp, 'translate_metadata', lambda metadata, *a, **kw: dict(metadata))

    def _default_translate(protected_md, **kwargs):
        stats_out = kwargs.get('stats_out')
        if stats_out is not None:
            stats_out.total_source_len = len(protected_md)
            stats_out.total_target_len = len(protected_md) + 5
            stats_out.total_chunks = 1
            stats_out.failed_chunks = 0
        return "# Глава\n\nПеревод текста"

    translate_mock = MagicMock(side_effect=translate or _default_translate)
    monkeypatch.setattr(cp, 'translate_chunks', translate_mock)

    def _default_build_output(translated_md, output_format, metadata, **kwargs):
        input_path = kwargs.get('input_path') or 'book'
        out = os.path.splitext(input_path)[0] + f".{output_format}"
        with open(out, 'w', encoding='utf-8') as f:
            f.write('OUTPUT')
        return out

    build_output_mock = MagicMock(side_effect=build_output or _default_build_output)
    monkeypatch.setattr(cp, 'build_output', build_output_mock)

    report = MagicMock()
    report.is_valid = validate_ok
    report.summary.return_value = "ok"
    report.issues = []
    monkeypatch.setattr(cp, 'validate_output', lambda *a, **kw: report)

    return translate_mock, build_output_mock


def _dump_paths(tmp_path, name="book", lang_marker="ru"):
    stem = str(tmp_path / name)
    return (
        f"{stem}_{lang_marker}.checkpoint.json",
        f"{stem}_{lang_marker}.translated.md",
        f"{stem}_{lang_marker}.meta.json",
    )


# ---------------------------------------------------------------------------
# 1. checkpoint_file reaches translate_chunks, with remove_on_success=False
# ---------------------------------------------------------------------------

def test_run_pipeline_passes_checkpoint_file_to_translate_chunks(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")

    translate_mock, _ = _install_mocks(monkeypatch)

    cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian",
                    skip_validation=True)

    assert translate_mock.call_count == 1
    kwargs = translate_mock.call_args.kwargs
    assert kwargs.get('checkpoint_file'), "run_pipeline must pass a real checkpoint_file"
    assert kwargs['checkpoint_file'].endswith('.checkpoint.json')
    assert kwargs.get('remove_on_success') is False, (
        "run_pipeline must keep the checkpoint until build_output/validate_output "
        "succeed, or a crash during EPUB assembly discards the translation"
    )
    assert kwargs.get('book_path') == str(input_path)


# ---------------------------------------------------------------------------
# 2. a build_output crash leaves the checkpoint + translated dump on disk
# ---------------------------------------------------------------------------

def test_checkpoint_and_dump_survive_build_output_crash(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")
    ckpt_path, dump_path, meta_path = _dump_paths(tmp_path)

    def _translate_leaving_checkpoint(protected_md, **kwargs):
        # Simulate what the real translate_chunks does when remove_on_success
        # is False: it leaves its checkpoint on disk once done.
        mgr = CheckpointManager(kwargs['checkpoint_file'])
        mgr.save(chunk_id=0, section_idx=0, chunk_idx=0, stats={},
                 total_source_len=10, total_target_len=12, synopsis_history={},
                 book_path=kwargs.get('book_path', ''),
                 start_time_iso='2024-01-01T00:00:00')
        stats_out = kwargs.get('stats_out')
        if stats_out is not None:
            stats_out.total_source_len = 10
            stats_out.total_target_len = 12
            stats_out.total_chunks = 1
        return "translated"

    def _crashing_build_output(*a, **kw):
        raise RuntimeError("pandoc exploded")

    _install_mocks(monkeypatch, translate=_translate_leaving_checkpoint,
                   build_output=_crashing_build_output)

    with pytest.raises(RuntimeError, match="pandoc exploded"):
        cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian")

    assert os.path.exists(ckpt_path), "checkpoint must survive a build_output crash"
    assert os.path.exists(dump_path), "translated Markdown must survive a build_output crash"
    assert os.path.exists(meta_path), "metadata dump must survive a build_output crash"

    with open(dump_path, 'r', encoding='utf-8') as f:
        assert f.read() == "translated"


# ---------------------------------------------------------------------------
# 3. successful build+validate cleans up checkpoint + dump
# ---------------------------------------------------------------------------

def test_successful_run_cleans_up_checkpoint_and_dump(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")
    ckpt_path, dump_path, meta_path = _dump_paths(tmp_path)

    def _translate_leaving_checkpoint(protected_md, **kwargs):
        mgr = CheckpointManager(kwargs['checkpoint_file'])
        mgr.save(chunk_id=0, section_idx=0, chunk_idx=0, stats={},
                 total_source_len=10, total_target_len=12, synopsis_history={},
                 book_path=kwargs.get('book_path', ''),
                 start_time_iso='2024-01-01T00:00:00')
        stats_out = kwargs.get('stats_out')
        if stats_out is not None:
            stats_out.total_source_len = 10
            stats_out.total_target_len = 12
            stats_out.total_chunks = 1
        return "translated"

    _install_mocks(monkeypatch, translate=_translate_leaving_checkpoint)

    cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian")

    assert not os.path.exists(ckpt_path), "checkpoint must be removed after a successful build"
    assert not os.path.exists(dump_path), "translated dump must be removed after a successful build"
    assert not os.path.exists(meta_path), "meta dump must be removed after a successful build"


# ---------------------------------------------------------------------------
# 4. the dump exists by the time build_output is entered
# ---------------------------------------------------------------------------

def test_dump_written_before_build_output_is_called(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")
    _, dump_path, meta_path = _dump_paths(tmp_path)

    seen = {}

    def _inspecting_build_output(translated_md, output_format, metadata, **kwargs):
        seen['dump_exists'] = os.path.exists(dump_path)
        seen['meta_exists'] = os.path.exists(meta_path)
        out = os.path.splitext(kwargs['input_path'])[0] + f".{output_format}"
        with open(out, 'w', encoding='utf-8') as f:
            f.write('OUTPUT')
        return out

    _install_mocks(monkeypatch, build_output=_inspecting_build_output)

    cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian",
                    skip_validation=True)

    assert seen['dump_exists'] is True
    assert seen['meta_exists'] is True


# ---------------------------------------------------------------------------
# 5. a second run reuses the dump: zero LLM calls
# ---------------------------------------------------------------------------

def test_second_run_reuses_dump_without_translating(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")

    translate_mock, _ = _install_mocks(monkeypatch)

    # Run 1: translates and dumps, but build_output "crashes" so the dump
    # survives (mirrors the real incident this recovers from).
    def _crashing_build_output(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(cp, 'build_output', MagicMock(side_effect=_crashing_build_output))
    with pytest.raises(RuntimeError):
        cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian")
    assert translate_mock.call_count == 1

    # Run 2: build_output now succeeds; translate_chunks must NOT be called
    # again — the whole point of the dump.
    _install_mocks(monkeypatch)  # re-installs translate_chunks as a fresh MagicMock too
    translate_mock_2 = cp.translate_chunks

    output = cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian",
                             skip_validation=True)

    assert translate_mock_2.call_count == 0, "reusing the dump must cost zero translate_chunks calls"
    assert os.path.exists(output)


# ---------------------------------------------------------------------------
# 6. fresh=True forces a full re-translation, ignoring any dump
# ---------------------------------------------------------------------------

def test_fresh_ignores_existing_dump(tmp_path, monkeypatch):
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")
    _, dump_path, meta_path = _dump_paths(tmp_path)

    # Pre-seed a dump as if a previous run had already finished translating.
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write("stale translation")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({"metadata": {"title": "Book"}, "translation_stats": {}}, f)
    # Make sure the dump looks newer than the input file.
    newer = os.path.getmtime(str(input_path)) + 10
    os.utime(dump_path, (newer, newer))

    translate_mock, _ = _install_mocks(monkeypatch)

    cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian",
                    skip_validation=True, fresh=True)

    assert translate_mock.call_count == 1, "fresh=True must ignore the dump and translate again"


def test_without_fresh_reuses_a_fresh_dump(tmp_path, monkeypatch):
    """Sanity check for test 6: without fresh=True, the same pre-seeded dump
    IS reused (so test 6 is actually exercising the fresh flag, not just
    always retranslating)."""
    input_path = tmp_path / "book.epub"
    input_path.write_bytes(b"fake")
    _, dump_path, meta_path = _dump_paths(tmp_path)

    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write("stale translation")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({"metadata": {"title": "Book"}, "translation_stats": {}}, f)
    newer = os.path.getmtime(str(input_path)) + 10
    os.utime(dump_path, (newer, newer))

    translate_mock, build_output_mock = _install_mocks(monkeypatch)

    cp.run_pipeline(str(input_path), output_format="epub", target_lang="russian",
                    skip_validation=True)

    assert translate_mock.call_count == 0
    # build_output must have received the reused dump's content verbatim.
    assert build_output_mock.call_args.args[0] == "stale translation"
