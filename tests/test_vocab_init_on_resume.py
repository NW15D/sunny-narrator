"""D3: vocabulary initialization must not be skipped on resume."""
import os


def test_vocab_init_not_gated_by_fresh_run():
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        source = f.read()
    assert 'engine.vocab_manager and resume_from_chunk == 0' not in source, \
        "vocab init is still gated by resume_from_chunk == 0"
    assert 'if engine.vocab_manager:' in source
