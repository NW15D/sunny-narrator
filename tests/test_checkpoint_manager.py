"""Tests for checkpoint_manager.py — save/load/resume with corruption recovery."""
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def make_manager(tmpdir):
    from checkpoint_manager import CheckpointManager
    path = os.path.join(tmpdir, 'checkpoint.json')
    return CheckpointManager(path), path


def sample_kwargs(**overrides):
    """Standard kwargs for CheckpointManager.save()."""
    kwargs = dict(
        chunk_id=5,
        section_idx=1,
        chunk_idx=2,
        stats={"successful": 5, "failed": 0, "total_tokens": 1234},
        total_source_len=1000,
        total_target_len=1100,
        synopsis_history={"sec0": "synopsis text"},
        book_path="/tmp/book.fb2",
        start_time_iso="2026-08-10T12:00:00",
    )
    kwargs.update(overrides)
    return kwargs


# ---------- exists() ----------

def test_exists_false_when_no_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        assert mgr.exists() is False


def test_exists_true_when_file_present():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        assert mgr.exists() is True


# ---------- remove() ----------

def test_remove_deletes_existing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        mgr.remove()
        assert not os.path.exists(path)


def test_remove_noop_when_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.remove()  # must not raise
        assert not os.path.exists(path)


# ---------- save() ----------

def test_save_creates_valid_checkpoint_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs())

        assert os.path.exists(path)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Bumped to 2 when checkpoints gained a fingerprint; asserted against
        # the constant so the version and the payload cannot drift apart.
        from checkpoint_manager import CHECKPOINT_VERSION
        assert data["version"] == CHECKPOINT_VERSION
        assert data["book_path"] == "/tmp/book.fb2"
        assert data["last_chunk"] == 5
        assert data["last_section_idx"] == 1
        assert data["last_chunk_idx"] == 2
        assert data["stats"]["successful"] == 5
        assert data["lengths"]["total_source_len"] == 1000
        assert data["lengths"]["total_target_len"] == 1100
        assert data["synopsis_history"] == {"sec0": "synopsis text"}
        assert data["created_at"] == "2026-08-10T12:00:00"
        assert "updated_at" in data


def test_save_no_extra_key_by_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs())
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert "extra" not in data


def test_save_with_extra():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs(extra={"custom": "value"}))
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["extra"] == {"custom": "value"}


def test_save_leaves_no_temp_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs())
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        assert tmp_files == []


def test_save_overwrites_previous_checkpoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs(chunk_id=1))
        mgr.save(**sample_kwargs(chunk_id=9))
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["last_chunk"] == 9


def test_save_atomic_original_intact_on_replace_failure():
    """If os.replace fails mid-write, original checkpoint must survive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs(chunk_id=1))
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()

        with patch('os.replace', side_effect=OSError("Disk full")):
            mgr.save(**sample_kwargs(chunk_id=99))  # failure is swallowed

        with open(path, 'r', encoding='utf-8') as f:
            assert f.read() == original
        # temp file must be cleaned up even on failure
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        assert tmp_files == []


def test_save_non_serializable_data_swallowed_no_file():
    """save() catches serialization errors; no checkpoint created, no temp left."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs(stats={"bad": object()}))
        assert not os.path.exists(path)
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        assert tmp_files == []


# ---------- load() ----------

def test_load_returns_none_when_no_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        assert mgr.load() is None


def test_load_returns_none_for_empty_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('')
        assert mgr.load() is None


def test_load_corrupt_json_returns_none_and_saves_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"version": 1, "truncated...')

        result = mgr.load()

        assert result is None
        # corrupt file moved to .corrupt backup, original path cleared
        assert not os.path.exists(path)
        assert os.path.exists(path + '.corrupt')


def test_load_non_utf8_bytes_returns_none_and_saves_backup():
    """Binary garbage (UnicodeDecodeError is a ValueError) is handled as corruption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        with open(path, 'wb') as f:
            f.write(b'\xff\xfe\x00\x01\x02corrupt')

        result = mgr.load()

        assert result is None
        assert not os.path.exists(path)
        assert os.path.exists(path + '.corrupt')


def test_load_corrupt_backup_preserves_original_bytes():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        garbage = '{not valid json at all'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(garbage)

        mgr.load()

        with open(path + '.corrupt', 'r', encoding='utf-8') as f:
            assert f.read() == garbage


# ---------- save/load roundtrip (resume path) ----------

def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)
        mgr.save(**sample_kwargs(extra={"vocab": "state"}))
        data = mgr.load()

        assert data is not None
        assert data["last_chunk"] == 5
        assert data["last_section_idx"] == 1
        assert data["last_chunk_idx"] == 2
        assert data["stats"]["total_tokens"] == 1234
        assert data["extra"] == {"vocab": "state"}


def test_load_after_corruption_recovery_cycle():
    """Corrupt → load() returns None and clears path → save() works again → load() succeeds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr, path = make_manager(tmpdir)

        with open(path, 'w', encoding='utf-8') as f:
            f.write('garbage')
        assert mgr.load() is None
        assert not mgr.exists()

        mgr.save(**sample_kwargs(chunk_id=42))
        data = mgr.load()
        assert data is not None
        assert data["last_chunk"] == 42


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
