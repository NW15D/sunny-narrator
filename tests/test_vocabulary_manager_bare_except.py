"""Bare except in VocabularyManager._atomic_write must not swallow
KeyboardInterrupt/SystemExit (BaseException subclasses)."""
import ast
import inspect
import textwrap
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.vocabulary_manager import VocabularyManager


def _make_vm(tmp_path):
    book = tmp_path / "TestBook.fb2"
    book.write_text("<FictionBook></FictionBook>", encoding="utf-8")
    return VocabularyManager(str(book))


def test_atomic_write_has_no_bare_except():
    """Source-level check: _atomic_write must not use a bare except handler."""
    source = textwrap.dedent(inspect.getsource(VocabularyManager._atomic_write))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            pytest.fail("bare 'except:' found in _atomic_write — "
                        "it catches KeyboardInterrupt/SystemExit")


def test_atomic_write_keyboard_interrupt_propagates(tmp_path, monkeypatch):
    """KeyboardInterrupt raised during write must propagate (not be swallowed)."""
    vm = _make_vm(tmp_path)

    def boom(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(os, "fdopen", boom)
    with pytest.raises(KeyboardInterrupt):
        vm._atomic_write("content")


def test_atomic_write_system_exit_propagates(tmp_path, monkeypatch):
    """SystemExit raised during write must propagate (not be swallowed)."""
    vm = _make_vm(tmp_path)

    def boom(*args, **kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(os, "fdopen", boom)
    with pytest.raises(SystemExit):
        vm._atomic_write("content")


def test_atomic_write_regular_exception_cleans_up_and_reraises(tmp_path, monkeypatch):
    """Regular Exception must trigger cleanup of temp file and re-raise."""
    vm = _make_vm(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fdopen", boom)
    with pytest.raises(OSError):
        vm._atomic_write("content")
    leftovers = [p for p in os.listdir(vm.book_dir) if p.endswith('.tmp')]
    assert leftovers == []
