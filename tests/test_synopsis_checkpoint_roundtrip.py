"""D2: synopsis history must survive checkpoint save/load roundtrip."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import TranslationEngine


def test_synopsis_roundtrip_through_checkpoint(tmp_path):
    engine = TranslationEngine(str(tmp_path / 'run1.fb2'))
    engine.synopsis_manager.add_chunk_result(0, 0, 'text one', generated_synopsis='SYN-A')
    engine.synopsis_manager.add_chunk_result(0, 1, 'text two', generated_synopsis='SYN-B')

    ckpt_file = str(tmp_path / 'book.checkpoint.json')
    engine.save_checkpoint(ckpt_file)
    with open(ckpt_file, 'r', encoding='utf-8') as f:
        checkpoint = json.load(f)

    engine2 = TranslationEngine(str(tmp_path / 'run2.fb2'))
    engine2.restore_from_checkpoint(checkpoint)

    restored = engine2.synopsis_manager.synopsis_cache
    assert 'section_0' in restored
    assert restored['section_0'] == ['SYN-A', 'SYN-B']
