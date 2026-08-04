"""D4: e2e resume — interrupt, restart, all translated content present."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import TranslationEngine, assemble_resume_content


def _chunks():
    out, gid = [], 0
    for s in range(2):
        for c in range(2):
            out.append({'chunk': f'SRC-{s}-{c}', 'section_idx': s,
                        'chunk_idx': c, 'global_id': gid})
            gid += 1
    return out


def _fake_translate(self, chunk, s_idx, c_idx, g_id, context):
    return (f'<p>TRANSLATED-{s_idx}-{c_idx}</p>', '')


def test_interrupt_resume_keeps_all_content(tmp_path, monkeypatch):
    tfile = str(tmp_path / 'out_tmp.fb2')
    ckpt = str(tmp_path / 'out.checkpoint.json')
    chunks = _chunks()

    monkeypatch.setattr(TranslationEngine, 'process_chunk_recursive', _fake_translate)

    # Run 1: translate first 2 chunks (section 0), then "crash"
    engine1 = TranslationEngine(tfile)
    engine1.process_all_chunks(chunks[:2], [], {}, tfile, ckpt)
    assert os.path.exists(ckpt)

    # Run 2: fresh engine resumes exactly like app.py main() does
    with open(ckpt, 'r', encoding='utf-8') as f:
        checkpoint = json.load(f)
    resume_from_chunk = checkpoint['last_chunk'] + 1
    assert resume_from_chunk == 2

    engine2 = TranslationEngine(tfile)
    engine2.restore_from_checkpoint(checkpoint)
    new_content = engine2.process_all_chunks(chunks[resume_from_chunk:], [], {}, tfile, ckpt)
    full = assemble_resume_content(new_content, resume_from_chunk, tfile)

    for s in range(2):
        for c in range(2):
            assert f'TRANSLATED-{s}-{c}' in full, f'chunk {s}-{c} lost on resume'
