"""COUNTRY: set in the samples, guessed with a warning for the languages whose
usage differs by country."""
import logging
import os

import pytest

from src.config import Config, country_matters, default_country

ROOT = os.path.join(os.path.dirname(__file__), '..')


@pytest.mark.parametrize("lang", ["spanish", "es", "portuguese", "pt", "zh", "english", "french", "german", "arabic"])
def test_countries_that_need_a_choice(lang):
    assert country_matters(lang)


@pytest.mark.parametrize("lang", ["russian", "turkish", "polish", "korean"])
def test_languages_of_one_country_need_none(lang):
    assert not country_matters(lang)


def test_no_country_for_spanish_warns(monkeypatch, caplog):
    monkeypatch.setenv("TARGET_LANG", "es")
    monkeypatch.delenv("COUNTRY", raising=False)
    with caplog.at_level(logging.WARNING, logger="src.config"):
        cfg = Config()
    assert cfg.country == default_country("es")
    assert any("COUNTRY is not set" in r.getMessage() for r in caplog.records)


def test_country_set_does_not_warn(monkeypatch, caplog):
    monkeypatch.setenv("TARGET_LANG", "es")
    monkeypatch.setenv("COUNTRY", "México")
    with caplog.at_level(logging.WARNING, logger="src.config"):
        cfg = Config()
    assert cfg.country == "México"
    assert not any("COUNTRY is not set" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("sample", ["env.sample", "env.cloud.sample"])
def test_samples_set_the_country(sample):
    text = open(os.path.join(ROOT, sample), encoding="utf-8").read()
    assert any(line.startswith("COUNTRY=") and line.strip() != "COUNTRY=" for line in text.splitlines())


@pytest.mark.parametrize("doc", ["README.md", "README_RU.md", "README_PT.md", "README_TR.md", "README_CN.md",
                                 "AGENTS.md", "docs/INSTALLATION.md"])
def test_docs_ask_for_the_country(doc):
    assert "COUNTRY" in open(os.path.join(ROOT, doc), encoding="utf-8").read()
