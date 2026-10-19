"""The default spaCy model of the source language is the largest installed one:
*_lg, else *_md, else *_sm; none installed: *_lg is downloaded, a smaller one
when that fails. NERMODEL is the user's choice and is never replaced."""
import spacy.util

from src import ner
from src.config import Config, model_size_chain


def _installed(monkeypatch, *names):
    monkeypatch.setattr(spacy.util, 'is_package', lambda name: name in names)


def test_the_chain_goes_from_the_size_of_the_name_down():
    assert model_size_chain('es_core_news_lg') == ['es_core_news_lg', 'es_core_news_md', 'es_core_news_sm']
    assert model_size_chain('es_core_news_md') == ['es_core_news_md', 'es_core_news_sm']
    assert model_size_chain('es_core_news_sm') == ['es_core_news_sm']
    assert model_size_chain('xx_ent_wiki_sm') == ['xx_ent_wiki_sm']
    assert model_size_chain('some_model') == ['some_model']


def test_the_default_is_the_largest_installed(monkeypatch):
    monkeypatch.delenv('NERMODEL', raising=False)
    monkeypatch.setenv('SOURCE_LANG', 'spanish')
    _installed(monkeypatch, 'es_core_news_md', 'es_core_news_sm')
    assert Config().nermodel == 'es_core_news_md'
    _installed(monkeypatch, 'es_core_news_lg', 'es_core_news_md', 'es_core_news_sm')
    assert Config().nermodel == 'es_core_news_lg'
    _installed(monkeypatch, 'es_core_news_sm')
    assert Config().nermodel == 'es_core_news_sm'
    _installed(monkeypatch)  # none: the large one, which is downloaded on first use
    assert Config().nermodel == 'es_core_news_lg'


def test_nermodel_of_the_user_is_kept(monkeypatch):
    monkeypatch.setenv('NERMODEL', 'es_core_news_sm')
    monkeypatch.setenv('SOURCE_LANG', 'spanish')
    _installed(monkeypatch, 'es_core_news_lg', 'es_core_news_sm')
    cfg = Config()
    assert cfg.nermodel == 'es_core_news_sm' and cfg.nermodel_explicit


def test_a_failed_download_of_the_large_model_falls_to_a_smaller_one(monkeypatch):
    installed, tried = set(), []

    def download(name):
        tried.append(name)
        if name.endswith('_sm'):
            installed.add(name)
        else:
            raise SystemExit(1)

    monkeypatch.setattr(spacy.util, 'is_package', lambda name: name in installed)
    monkeypatch.setattr(ner.spacy.cli, 'download', download)
    monkeypatch.setattr(ner.config, 'spacy_auto_download', True)
    monkeypatch.setattr(ner.config, 'nermodel', 'es_core_news_lg')
    monkeypatch.setattr(ner.config, 'nermodel_explicit', False, raising=False)
    assert ner.ensure_model('es_core_news_lg')
    assert tried == ['es_core_news_lg', 'es_core_news_md', 'es_core_news_sm']
    assert ner.config.nermodel == 'es_core_news_sm'


def test_an_installed_smaller_model_is_used_without_a_download(monkeypatch):
    _installed(monkeypatch, 'es_core_news_md')
    monkeypatch.setattr(ner.spacy.cli, 'download', lambda name: (_ for _ in ()).throw(AssertionError(name)))
    monkeypatch.setattr(ner.config, 'spacy_auto_download', True)
    assert ner._install_model('es_core_news_lg') == 'es_core_news_md'
