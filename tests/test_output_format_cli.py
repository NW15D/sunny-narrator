"""--output-format / OUTPUT_FORMAT for the classic (FB2/TXT) pipeline."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import resolve_classic_output_format


def test_cli_flag_wins_over_config():
    assert resolve_classic_output_format('epub', 'fb2') == 'epub'
    assert resolve_classic_output_format('FB2', 'epub') == 'fb2'


def test_config_value_is_used_without_a_flag():
    assert resolve_classic_output_format(None, 'epub') == 'epub'
    assert resolve_classic_output_format(None, 'fb2') == 'fb2'
    assert resolve_classic_output_format(None, '') == 'fb2'


def test_explicit_unsupported_flag_is_an_error():
    with pytest.raises(ValueError, match='fb2 or epub'):
        resolve_classic_output_format('docx', 'fb2')


def test_leftover_config_value_falls_back_to_fb2():
    assert resolve_classic_output_format(None, 'pdf') == 'fb2'


def test_config_accepts_all_pipeline_formats(monkeypatch):
    from src.config import Config
    for fmt in ('fb2', 'epub', 'docx', 'pdf'):
        monkeypatch.setenv('OUTPUT_FORMAT', fmt)
        assert Config().output_format == fmt
    monkeypatch.setenv('OUTPUT_FORMAT', 'mobi')
    assert Config().output_format == 'fb2'
