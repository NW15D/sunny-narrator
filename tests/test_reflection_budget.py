"""REFLECTION, the stage that loops, gets max_tokens from the translation it
reviews (every sentence may get a fix) and the tokens per character learned
from the proofread model's own answers, not the whole MAX_TOKENS_PER_CHUNK."""
import pytest

from src import utils


@pytest.fixture
def calibration(monkeypatch):
    monkeypatch.setattr(utils.config, 'nothink_proofread', True)
    cal = utils.TokenCalibration()
    monkeypatch.setattr(utils, 'token_calibration', cal)
    return cal


def _expected(text, per_char):
    sentences = max(1, len(utils._SENTENCE_END.findall(text)))
    return int((2 * len(text) + utils.REFLECTION_CHARS_PER_FIX * sentences) * per_char)


def test_budget_follows_the_translation(calibration):
    assert utils.reflection_token_budget("Короткая фраза.") == utils.REFLECTION_MIN_TOKENS
    text = "Он открыл дверь и вошёл в комнату. " * 50
    assert utils.reflection_token_budget(text) == _expected(text, utils.TokenCalibration.DEFAULT)
    assert utils.reflection_token_budget("а. " * 10 ** 5) == utils.MAX_TOKENS_PER_CHUNK


def test_budget_uses_the_calibrated_tokens_per_char(calibration):
    for _ in range(utils.TokenCalibration.WARMUP):
        calibration.record('proofread', 600, "я" * 1000)
    calibration.record('translate', 100, "я" * 1000)  # another role does not count
    text = "Он открыл дверь и вошёл в комнату. " * 50
    assert calibration.tokens_per_char('proofread') == pytest.approx(0.6)
    assert utils.reflection_token_budget(text) == _expected(text, 0.6)


def test_short_answers_do_not_calibrate(calibration):
    for _ in range(5):
        calibration.record('proofread', 90, "я" * 100)
    assert calibration.tokens_per_char('proofread') == utils.TokenCalibration.DEFAULT


def test_no_cut_with_thinking_on(calibration, monkeypatch):
    monkeypatch.setattr(utils.config, 'nothink_proofread', False)
    assert utils.reflection_token_budget("а" * 100) == utils.MAX_TOKENS_PER_CHUNK


def test_reflection_call_uses_the_budget(calibration, monkeypatch):
    monkeypatch.setattr(utils.config, 'json_mode', True)
    seen = {}

    def fake_complete(**kwargs):
        seen.update(kwargs)
        return '{"fixes": []}', 1

    monkeypatch.setattr(utils.llm_service, 'complete', fake_complete)
    ctx = utils.TranslationContext(source_lang='english', target_lang='russian',
                                   source_text='Hello.', country='Россия')
    text = "Он открыл дверь и вошёл в комнату. " * 50
    utils.TranslationPipeline().reflection(ctx, text)
    assert seen['max_tokens'] == utils.reflection_token_budget(text)
