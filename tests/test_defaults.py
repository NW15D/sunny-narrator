"""The code defaults: English -> French, readers in France."""
from src.config import Config


def test_default_languages_and_country(monkeypatch):
    for name in ('SOURCE_LANG', 'TARGET_LANG', 'COUNTRY'):
        monkeypatch.delenv(name, raising=False)
    cfg = Config()
    assert (cfg.source_lang, cfg.target_lang, cfg.country) == ('english', 'french', 'France')
