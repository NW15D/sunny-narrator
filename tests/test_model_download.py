"""
A fresh install has no spaCy models: the dictionary check before a
translation and the gender check of the translation download theirs on first
use (ner.ensure_model) instead of being skipped for the whole run, as a clean
cloud install showed ("Dictionary check skipped: spaCy model 'en_core_web_lg'
is not available", the GENDER stage silently off).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import spacy.cli
import spacy.util

from src import dict_review, gender_check, ner


def _no_models(monkeypatch, downloaded):
    installed = set()
    monkeypatch.setattr(spacy.util, 'is_package', lambda name: name in installed)

    def download(name):
        downloaded.append(name)
        installed.add(name)

    monkeypatch.setattr(spacy.cli, 'download', download)


def test_a_missing_model_is_downloaded_once(monkeypatch):
    downloaded = []
    _no_models(monkeypatch, downloaded)
    monkeypatch.setattr(ner.config, 'spacy_auto_download', True)
    assert ner.ensure_model("en_core_web_lg") and ner.ensure_model("en_core_web_lg")
    assert downloaded == ["en_core_web_lg"]


def test_no_download_when_turned_off_or_failing(monkeypatch):
    downloaded = []
    _no_models(monkeypatch, downloaded)
    assert not ner.ensure_model("en_core_web_lg")  # SPACY_AUTO_DOWNLOAD=false (tests)
    assert downloaded == []

    def offline(name):
        raise SystemExit(1)  # what spacy.cli.download does when it fails

    monkeypatch.setattr(ner.config, 'spacy_auto_download', True)
    monkeypatch.setattr(spacy.cli, 'download', offline)
    assert not ner.ensure_model("en_core_web_lg")


def test_the_dictionary_check_asks_for_its_model(monkeypatch):
    asked = []
    monkeypatch.setattr(ner, 'ensure_model', lambda name: asked.append(name) or False)
    assert dict_review._load_model("en_core_web_nonexistent") is None
    assert asked == ["en_core_web_nonexistent"]


def test_the_gender_check_downloads_only_what_spacy_publishes(monkeypatch):
    asked = []
    monkeypatch.setattr(spacy.util, 'is_package', lambda name: False)
    monkeypatch.setattr(ner, 'ensure_model', lambda name: asked.append(name) or False)
    gender_check._target_nlp.cache_clear()
    try:
        assert gender_check._target_nlp('ru') is None
        assert gender_check._target_nlp('he') is None  # no spaCy pipeline: nothing to fetch
    finally:
        gender_check._target_nlp.cache_clear()
    assert asked == ["ru_core_news_sm"]
