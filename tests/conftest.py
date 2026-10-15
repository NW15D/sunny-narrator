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
