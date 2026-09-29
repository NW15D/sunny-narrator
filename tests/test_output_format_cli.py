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


def test_console_script_points_at_the_cli_not_at_main():
    """`sunny-narrator` must route by file type and parse flags like `python app.py`."""
    import tomllib
    import app
    with open(os.path.join(os.path.dirname(__file__), '..', 'pyproject.toml'), 'rb') as f:
        target = tomllib.load(f)['project']['scripts']['sunny-narrator']
    module, func = target.split(':')
    assert (module, func) == ('app', 'cli')
    assert callable(getattr(app, func))


def test_app_module_is_packaged_for_the_console_script():
    """Without py-modules the installed script cannot import `app` outside the repo."""
    import tomllib
    with open(os.path.join(os.path.dirname(__file__), '..', 'pyproject.toml'), 'rb') as f:
        setuptools_cfg = tomllib.load(f)['tool']['setuptools']
    assert 'app' in setuptools_cfg.get('py-modules', [])


def test_installed_console_script_runs_outside_the_repo(tmp_path):
    import shutil
    import subprocess
    script = shutil.which('sunny-narrator', path=os.path.dirname(sys.executable))
    if script is None:
        pytest.skip('package is not installed in this environment')
    env = dict(os.environ, API_KEY_TRANSLATE='t', API_KEY_PROOFREAD='t', API_KEY_IMAGES='t')
    result = subprocess.run([script, '--help'], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert 'usage: sunny-narrator' in result.stdout
