"""B7/C11: any untranslated chunk must fail the translation by default."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

CHUNKS = [
    'The quick brown fox jumps over the lazy dog near the river bank.',
    'A gentle breeze moved through the tall green trees in the forest.',
    'The old library kept thousands of books on its wooden shelves.',
    'Morning light slowly filled the quiet empty streets of the town.',
]
TRANSLATIONS = {
    CHUNKS[1]: 'Лёгкий ветерок двигался сквозь высокие зелёные деревья в лесу.',
    CHUNKS[2]: 'Старая библиотека хранила тысячи книг на своих деревянных полках.',
    CHUNKS[3]: 'Утренний свет медленно заполнял тихие пустые улицы городка.',
}


def test_single_failed_chunk_aborts(monkeypatch):
    import src.calibre_pipeline as cp

    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda *a, **kw: CHUNKS)

    class _State:
        def __init__(self, text):
            self.final_translation = text
            self.synopsis = ''

    def _execute(**kwargs):
        src_text = kwargs.get('source_text')
        if src_text not in TRANSLATIONS:
            raise RuntimeError('LLM down')
        return _State(TRANSLATIONS[src_text])

    fake_pipeline = type('P', (), {})()
    fake_pipeline.execute = staticmethod(_execute)
    monkeypatch.setattr(cp, '_pipeline', fake_pipeline)
    monkeypatch.setattr(cp.time, 'sleep', lambda s: None)

    with pytest.raises(RuntimeError):
        cp.translate_chunks('some text to translate')
