"""Tests for ner.py import robustness and bare-except removal (audit fixes 2026-07-23)."""
import importlib
import re
import sys
from pathlib import Path

import pytest

NER_PATH = Path(__file__).resolve().parent.parent / "src" / "ner.py"


def _fresh_import_ner(monkeypatch):
    """Import src.ner fresh, forcing cupy to be unavailable."""
    # Force `import cupy` inside ner.py to raise ImportError
    monkeypatch.setitem(sys.modules, "cupy", None)
    # Remove cached module so the import machinery re-executes ner.py
    for mod in list(sys.modules):
        if mod == "src.ner" or mod.endswith(".ner"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import src.ner as ner
    importlib.reload(ner)
    return ner


def test_ner_imports_without_cupy(monkeypatch):
    """ner.py must import cleanly even when CuPy is not installed."""
    ner = _fresh_import_ner(monkeypatch)
    assert getattr(ner, "CUPY_AVAILABLE") is False
    assert ner.cp is None


def test_gpu_function_raises_without_cupy(monkeypatch):
    """The GPU cosine-similarity function must raise a clear RuntimeError without CuPy."""
    ner = _fresh_import_ner(monkeypatch)
    with pytest.raises(RuntimeError, match="CuPy is required"):
        ner.find_matching_words_with_cosine_similarity("some text", {"k": {"en": "word"}}, "en")


def test_bare_except_replaced():
    """No bare `except:` clauses should remain in ner.py."""
    source = NER_PATH.read_text(encoding="utf-8")
    # Match `except:` (bare) but not `except Something:` or `except (a, b):`
    bare_excepts = re.findall(r"^\s*except\s*:", source, flags=re.MULTILINE)
    assert bare_excepts == [], f"Found bare except clauses: {bare_excepts}"
