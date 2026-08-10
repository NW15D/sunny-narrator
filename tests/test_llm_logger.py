"""Tests for src/llm_logger.py — LLM call logging."""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm_logger import LLMLogger, LLMCallLog, init_llm_logger, get_llm_logger, log_llm_call


CALL_KWARGS = dict(
    stage="INITIAL",
    role="PRIMARY",
    model="test-model",
    temperature=0.7,
    duration_ms=123,
    tokens_input=10,
    tokens_output=20,
    tokens_total=30,
    prompt_system="You are a translator.",
    prompt_user="Translate this.",
    response="Перевод.",
)


class TestLLMCallLog:
    def test_to_dict(self):
        log = LLMCallLog(timestamp="2026-08-10T12:00:00", **CALL_KWARGS)
        d = log.to_dict()
        assert d["stage"] == "INITIAL"
        assert d["model"] == "test-model"
        assert d["temperature"] == 0.7
        assert d["tokens_total"] == 30
        assert d["timestamp"] == "2026-08-10T12:00:00"
        assert set(d.keys()) == {
            "timestamp", "stage", "role", "model", "temperature",
            "duration_ms", "tokens_input", "tokens_output", "tokens_total",
            "prompt_system", "prompt_user", "response",
        }


class TestLLMLogger:
    def test_creates_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        LLMLogger(log_dir=str(log_dir))
        assert log_dir.is_dir()

    def test_disabled_does_not_create_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        LLMLogger(log_dir=str(log_dir), enabled=False)
        assert not log_dir.exists()

    def test_log_call_creates_jsonl_file(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        logger.log_call(**CALL_KWARGS)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = tmp_path / f"llm_calls_{today}.log"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["stage"] == "INITIAL"
        assert entry["role"] == "PRIMARY"
        assert entry["model"] == "test-model"
        assert entry["prompt_user"] == "Translate this."
        assert entry["response"] == "Перевод."
        # timestamp is valid ISO format
        datetime.fromisoformat(entry["timestamp"])

    def test_log_call_appends(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        logger.log_call(**CALL_KWARGS)
        logger.log_call(**{**CALL_KWARGS, "stage": "REFLECTION"})
        today = datetime.now().strftime("%Y-%m-%d")
        lines = (tmp_path / f"llm_calls_{today}.log").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["stage"] == "REFLECTION"

    def test_log_call_disabled_no_file(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path), enabled=False)
        logger.log_call(**CALL_KWARGS)
        assert list(tmp_path.glob("*.log")) == []

    def test_none_prompts_become_empty_strings(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        logger.log_call(**{**CALL_KWARGS, "prompt_system": None, "response": None})
        today = datetime.now().strftime("%Y-%m-%d")
        entry = json.loads((tmp_path / f"llm_calls_{today}.log").read_text(encoding="utf-8").strip())
        assert entry["prompt_system"] == ""
        assert entry["response"] == ""

    def test_unicode_roundtrip(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        text = "Русский текст с эмодзи 🎉 и символами — «ёлка»"
        logger.log_call(**{**CALL_KWARGS, "response": text})
        today = datetime.now().strftime("%Y-%m-%d")
        raw = (tmp_path / f"llm_calls_{today}.log").read_text(encoding="utf-8")
        # ensure_ascii=False means unicode stored as-is
        assert text in raw
        entry = json.loads(raw.strip())
        assert entry["response"] == text

    def test_get_today_log_path(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        path = logger.get_today_log_path()
        today = datetime.now().strftime("%Y-%m-%d")
        assert path == tmp_path / f"llm_calls_{today}.log"

    def test_get_today_log_path_disabled(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path), enabled=False)
        assert logger.get_today_log_path() is None

    def test_get_recent_logs_empty(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        assert logger.get_recent_logs() == []

    def test_get_recent_logs_disabled(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path), enabled=False)
        assert logger.get_recent_logs() == []

    def test_get_recent_logs_filters_by_days(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        # Dates relative to now so the test never goes stale:
        now = datetime.now()
        inside = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        outside = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        (tmp_path / f"llm_calls_{inside}.log").write_text("{}\n")
        (tmp_path / f"llm_calls_{outside}.log").write_text("{}\n")
        # non-matching filename — should be skipped
        (tmp_path / "llm_calls_notadate.log").write_text("{}\n")
        # unrelated file — should be ignored by glob
        (tmp_path / "other.log").write_text("{}\n")
        recent = logger.get_recent_logs(days=7)
        names = [f.name for f in recent]
        assert f"llm_calls_{inside}.log" in names
        assert f"llm_calls_{outside}.log" not in names
        assert "llm_calls_notadate.log" not in names

    def test_get_recent_logs_sorted_desc(self, tmp_path):
        logger = LLMLogger(log_dir=str(tmp_path))
        # Dates relative to now so the test never goes stale:
        now = datetime.now()
        offsets = [5, 1, 3]  # days ago, deliberately unsorted
        dates = [(now - timedelta(days=n)).strftime("%Y-%m-%d") for n in offsets]
        for d in dates:
            (tmp_path / f"llm_calls_{d}.log").write_text("{}\n")
        recent = logger.get_recent_logs(days=365)
        expected = [
            f"llm_calls_{(now - timedelta(days=n)).strftime('%Y-%m-%d')}.log"
            for n in sorted(offsets)
        ]
        assert [f.name for f in recent] == expected

    def test_write_error_does_not_raise(self, tmp_path):
        """Logging failure must not break the application."""
        logger = LLMLogger(log_dir=str(tmp_path))
        # Make the target path a directory so open() fails
        today = datetime.now().strftime("%Y-%m-%d")
        (tmp_path / f"llm_calls_{today}.log").mkdir()
        logger.log_call(**CALL_KWARGS)  # must not raise

    def test_date_rotation(self, tmp_path, monkeypatch):
        """Log file changes when date changes."""
        logger = LLMLogger(log_dir=str(tmp_path))
        logger.log_call(**CALL_KWARGS)

        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2030, 1, 15, 10, 0, 0)

        monkeypatch.setattr("llm_logger.datetime", FakeDatetime)
        logger.log_call(**CALL_KWARGS)
        assert (tmp_path / "llm_calls_2030-01-15.log").exists()
        assert logger._current_date == "2030-01-15"


class TestGlobalLogger:
    def test_init_and_get(self, tmp_path):
        instance = init_llm_logger(log_dir=str(tmp_path), enabled=True)
        assert get_llm_logger() is instance

    def test_log_llm_call_uses_global(self, tmp_path):
        init_llm_logger(log_dir=str(tmp_path))
        log_llm_call(**CALL_KWARGS)
        today = datetime.now().strftime("%Y-%m-%d")
        assert (tmp_path / f"llm_calls_{today}.log").exists()

    def test_log_llm_call_without_init_is_noop(self):
        import llm_logger
        old = llm_logger._llm_logger
        llm_logger._llm_logger = None
        try:
            log_llm_call(**CALL_KWARGS)  # must not raise
        finally:
            llm_logger._llm_logger = old
