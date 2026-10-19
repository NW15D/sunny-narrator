"""Config() must not mutate the environment, and .env values stay reachable.

Root cause (review DEF-C1): Config.__init__ called load_dotenv() on every
construction, so a name deleted from os.environ came back from the checkout's
.env (COUNTRY=Россия, NERMODEL=en_core_web_lg there) and the suite's outcome
depended on the developer's local .env - green on CI, red on this box. The
file is now read once, at import of src.config; a real environment variable
wins over it; constructing a Config() changes nothing.
"""
import os

from src.config import Config


def test_construction_does_not_mutate_the_environment(monkeypatch):
    """The four .env-refill failures in one place: a deleted name stays
    deleted (the language-derived default is used) and os.environ is not
    written to by construction."""
    monkeypatch.delenv("COUNTRY", raising=False)
    monkeypatch.delenv("NERMODEL", raising=False)
    monkeypatch.setenv("SOURCE_LANG", "turkish")
    monkeypatch.setenv("TARGET_LANG", "turkish")
    before = dict(os.environ)
    cfg = Config()
    assert dict(os.environ) == before, "Config() must not write to os.environ"
    assert cfg.country == "Türkiye"           # the .env COUNTRY must not come back
    assert cfg.nermodel == "xx_ent_wiki_sm"   # neither must NERMODEL
    assert "COUNTRY" not in os.environ and "NERMODEL" not in os.environ


def test_env_var_wins_over_the_file(monkeypatch):
    monkeypatch.setenv("COUNTRY", "Kıbrıs")
    assert Config().country == "Kıbrıs"


def test_explicit_env_path_still_loads(monkeypatch, tmp_path):
    """Config(env_path=...) keeps its documented contract."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("MODEL_TRANSLATE=custom-model\n", encoding="utf-8")
    monkeypatch.delenv("MODEL_TRANSLATE", raising=False)
    try:
        cfg = Config(env_path=str(env_file))
        assert cfg.model_translate == "custom-model"
    finally:
        os.environ.pop("MODEL_TRANSLATE", None)
