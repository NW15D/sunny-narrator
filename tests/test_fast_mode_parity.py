"""FAST_TRANS / --fast-mode and --fresh act the same in both pipelines.

The Calibre path (DOCX/EPUB/PDF) used to take fast mode only from the CLI
flag, so FAST_TRANS in .env was ignored there; --fresh worked only there.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app
import src.calibre_pipeline as cp


def _run_cli(monkeypatch, tmp_path, ext, argv, fast_trans):
    book = tmp_path / f"book{ext}"
    book.write_bytes(b"fake")
    monkeypatch.setattr(app.config, 'myfile', str(book))
    monkeypatch.setattr(app.config, 'output_format', 'epub')
    monkeypatch.setattr(app.config, 'fast_trans', fast_trans)
    monkeypatch.setattr(sys, 'argv', ['app.py', *argv])
    seen = {}

    def fake_run_pipeline(**kw):
        seen.update(fast_mode=kw['fast_mode'], fresh=kw['fresh'])
        return str(tmp_path / "out.epub")

    def fake_main(fresh=False):
        seen.update(fast_mode=app.config.fast_trans, fresh=fresh)

    monkeypatch.setattr(cp, 'check_calibre_installed', lambda: True)
    monkeypatch.setattr(cp, 'run_pipeline', fake_run_pipeline)
    monkeypatch.setattr(app, 'main', fake_main)
    try:
        app.cli()
    except SystemExit as e:
        assert e.code in (0, None)
    return seen


@pytest.mark.parametrize("ext", [".epub", ".fb2"])
@pytest.mark.parametrize("argv, fast_trans, expected", [
    ([], True, True),                 # FAST_TRANS=on in .env
    ([], False, False),               # FAST_TRANS=false
    (['--fast-mode'], False, True),   # the flag turns it on
])
def test_fast_mode_comes_from_the_same_setting(monkeypatch, tmp_path, ext, argv, fast_trans, expected):
    assert _run_cli(monkeypatch, tmp_path, ext, argv, fast_trans)['fast_mode'] is expected


@pytest.mark.parametrize("ext", [".epub", ".fb2"])
def test_fresh_reaches_both_pipelines(monkeypatch, tmp_path, ext):
    assert _run_cli(monkeypatch, tmp_path, ext, ['--fresh'], False)['fresh'] is True
    assert _run_cli(monkeypatch, tmp_path, ext, [], False)['fresh'] is False
