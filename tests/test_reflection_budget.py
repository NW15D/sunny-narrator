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
    # The budget clamps at MAX_TOKENS_PER_CHUNK, and the clamp is deliberate
    # (b7a969d/a04ef95: a looping REFLECTION answer is cut sooner). The cap is
    # 2 x MAX_LEN_CHUNK, and MAX_LEN_CHUNK comes from the checkout's .env, so
    # do not pin 6900: compare against the cap this checkout applies.
    assert utils.reflection_token_budget(text) == min(utils.MAX_TOKENS_PER_CHUNK,
                                                      _expected(text, 0.6))


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


def test_presence_penalty_is_sent_for_each_role_and_reflection(monkeypatch):
    """A server default (llama.cpp, Qwen preset: 1.5) penalizes the tokens of
    a word just written: a stage that writes the text again puts a Latin
    twin in. REFLECTION keeps a penalty of its own: without one its list of
    fixes repeats until max_tokens."""
    monkeypatch.setattr(utils.config, 'presence_penalty_translate', 0.0)
    monkeypatch.setattr(utils.config, 'presence_penalty_proofread', 0.3)
    monkeypatch.setattr(utils.config, 'presence_penalty_reflection', 1.5)
    sent = []

    class Choice:
        finish_reason = 'stop'

        class message:
            content = 'ok'

    class Response:
        choices = [Choice]
        usage = None
        model = 'm'

    def create(**kwargs):
        sent.append(kwargs['presence_penalty'])
        return Response

    for client in (utils.llm_service._translate_client, utils.llm_service._proofread_client):
        monkeypatch.setattr(client.chat.completions, 'create', create)
    utils.llm_service.complete(role=utils.LLMRole.TRANSLATE, system_prompt='s', user_prompt='u')
    utils.llm_service.complete(role=utils.LLMRole.PROOFREAD, system_prompt='s', user_prompt='u')
    utils.llm_service.complete(role=utils.LLMRole.PROOFREAD, system_prompt='s', user_prompt='u',
                               stage=utils.TranslationStage.REFLECTION)
    assert sent == [0.0, 0.3, 1.5]


def test_truncated_call_is_logged_before_it_fails(monkeypatch):
    """A call cut off by max_tokens (the model looped) is the one to study:
    it must reach llm_calls_*.log, not only raise."""
    logged = []

    class Choice:
        finish_reason = 'length'

        class message:
            content = 'зациклился зациклился'

    class Usage:
        total_tokens, prompt_tokens, completion_tokens = 9000, 1000, 8000

    class Response:
        choices = [Choice]
        usage = Usage
        model = 'm'

    retry_before = utils.metrics.retry_tokens
    monkeypatch.setattr(utils.config, 'llm_logging_enabled', True)
    monkeypatch.setattr(utils, 'log_llm_call', lambda **kw: logged.append(kw))
    monkeypatch.setattr(utils.llm_service._proofread_client.chat.completions, 'create',
                        lambda **kw: Response)
    with pytest.raises(utils.TruncatedResponseError):
        utils.llm_service.complete(role=utils.LLMRole.PROOFREAD, system_prompt='s', user_prompt='u',
                                   stage=utils.TranslationStage.IMPROVE)
    assert [c['stage'] for c in logged] == ['improve:length']
    assert logged[0]['response'] == 'зациклился зациклился'
    assert logged[0]['tokens_output'] == 8000
    assert utils.metrics.retry_tokens - retry_before == 9000, "the tokens spent for nothing are counted"
