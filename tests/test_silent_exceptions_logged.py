"""Tests that previously silent ``except ...: pass`` blocks now emit log records."""

import logging
from unittest import mock

from src import txt_handler
from src.fb2_handler import _read_file_with_encoding_fallback


def test_txt_handler_logs_decode_fallbacks(tmp_path, caplog):
    """0x98 is invalid in UTF-8 and undefined in cp1251 -> both fallbacks log."""
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\x98")

    with mock.patch.object(txt_handler, "detect_encoding", None):
        with caplog.at_level(logging.DEBUG, logger="src.txt_handler"):
            result = txt_handler._read_with_fallback(str(path))

    assert result == "\x98"  # latin-1 last resort, behaviour unchanged
    messages = [r.getMessage() for r in caplog.records if r.name == "src.txt_handler"]
    assert any("UTF-8 decode failed" in m for m in messages)
    assert any("cp1251 decode failed" in m for m in messages)


def test_fb2_handler_logs_utf8_decode_failure(tmp_path, caplog):
    path = tmp_path / "bad.fb2"
    path.write_bytes(b"\xff\xfe some non-utf8 content")

    with caplog.at_level(logging.DEBUG, logger="src.fb2_handler"):
        content = _read_file_with_encoding_fallback(str(path))

    assert content  # behaviour unchanged: file still read via fallback
    messages = [r.getMessage() for r in caplog.records if r.name == "src.fb2_handler"]
    assert any("UTF-8 decode failed" in m for m in messages)
