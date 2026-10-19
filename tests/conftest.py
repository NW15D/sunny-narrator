import os

# The tests were written for English -> Russian; the code defaults are
# English -> French. Pin the pair before src.config is first imported
# (tests/test_defaults.py checks the real defaults on a fresh Config).
os.environ.setdefault('SOURCE_LANG', 'english')
os.environ.setdefault('TARGET_LANG', 'russian')

import pytest


@pytest.fixture(autouse=True)
def _reset_length_calibration():
    # Learned length ratios are module-level state; keep tests independent.
    from src.utils import length_calibration
    length_calibration.reset()
    yield
    length_calibration.reset()


@pytest.fixture(autouse=True)
def _no_dictionary_check(monkeypatch):
    # The check before a translation parses the whole book with the source
    # spaCy model; tests that load a dictionary do not need it.
    # tests/test_dict_review.py turns it on where it is the subject.
    import src.vocabulary_manager as vm
    monkeypatch.setattr(vm.config, 'dict_check', False)


@pytest.fixture(autouse=True)
def _no_model_downloads(monkeypatch):
    # A missing spaCy model is downloaded on first use (ner.ensure_model);
    # tests skip without their models instead of fetching hundreds of MB.
    import src.ner as ner
    monkeypatch.setattr(ner.config, 'spacy_auto_download', False)


@pytest.fixture(autouse=True)
def _fresh_gender_tally():
    # The run's tally of gendered sentences (GENDER stage) is global state.
    from src.utils import metrics
    for tally in (metrics.gender_agree, metrics.gender_against, metrics.gender_of,
                  metrics.gender_warned):
        tally.clear()
    yield
