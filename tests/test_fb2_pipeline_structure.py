"""Classic pipeline: section tree on output, incremental file, resume, local chunk repair."""
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app as app_module
import src.fb2_handler as fb2
import src.xmlcheck as xc
from app import TranslationEngine, assemble_resume_content
from src.fb2_structure import close_dangling_sections

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
TAIL = '<p>Tail of part one after its sections (odd but seen in the wild).</p>'
MAX_LEN = 90
_REAL_PROCESS_CHUNK_RECURSIVE = TranslationEngine.process_chunk_recursive


def _identity(self, chunk, s_idx, c_idx, g_id, context):
    return chunk, ''


@pytest.fixture(autouse=True)
def _identity_translation(monkeypatch):
    monkeypatch.setattr(TranslationEngine, 'process_chunk_recursive', _identity)


def _prepare(valid=True, max_len=MAX_LEN):
    body, header, footer = fb2.parse_xml(RICH)
    if valid:
        body = body.replace(TAIL, '').replace('9lonely', 'lonely')
    sections, meta = fb2.prepare_body_structure(body, max_len)
    chunks, gid = [], 0
    for s, unit in enumerate(sections):
        for c, chunk in enumerate(unit):
            chunks.append({'chunk': chunk, 'section_idx': s, 'chunk_idx': c, 'global_id': gid})
            gid += 1
    return body, header, footer, sections, meta, chunks


def _run(tmp_path, chunks, sections, meta, name='out', restore=None):
    tfile, ckpt = str(tmp_path / f'{name}_tmp.fb2'), str(tmp_path / f'{name}.checkpoint.json')
    engine = TranslationEngine(tfile)
    if restore:
        engine.restore_from_checkpoint(restore)
    content = engine.process_all_chunks(chunks, sections, {}, tfile, ckpt, section_meta=meta)
    return engine, content, tfile, ckpt


def test_identity_translation_reproduces_the_section_tree(tmp_path):
    # large enough that no poem/cite has to be split into two containers
    body, header, footer, sections, meta, chunks = _prepare(max_len=400)
    _engine, content, tfile, _ckpt = _run(tmp_path, chunks, sections, meta)

    assert re.sub(r'\s+', '', content) == re.sub(r'\s+', '', body)
    assert open(tfile, encoding='utf-8').read() == content
    assert xc.validate_fb2(f"{header}<body>\n{content}</body>\n{footer}") == []


def test_invalid_source_shapes_survive_too(tmp_path):
    body, _h, _f, sections, meta, chunks = _prepare(valid=False, max_len=400)
    _engine, content, _tfile, _ckpt = _run(tmp_path, chunks, sections, meta)
    assert re.sub(r'\s+', '', content) == re.sub(r'\s+', '', body)
    assert 'Tail of part one' in content


def test_resume_from_every_possible_cut_gives_the_same_book(tmp_path):
    _body, _h, _f, sections, meta, chunks = _prepare()
    _engine, full, _tfile, _ckpt = _run(tmp_path, chunks, sections, meta, name='full')
    assert len(chunks) > 8

    for cut in range(1, len(chunks)):
        name = f'cut{cut}'
        _e1, _partial, tfile, ckpt = _run(tmp_path, chunks[:cut], sections, meta, name=name)
        with open(ckpt, encoding='utf-8') as f:
            checkpoint = json.load(f)
        resume_from = checkpoint['last_chunk'] + 1
        engine2 = TranslationEngine(tfile)
        engine2.restore_from_checkpoint(checkpoint)
        new = engine2.process_all_chunks(chunks[resume_from:], sections, {}, tfile, ckpt, section_meta=meta)
        assert assemble_resume_content(new, resume_from, tfile) == full, f'cut after {cut} chunks'


def test_half_written_chunk_is_cut_off_on_resume(tmp_path):
    _body, _h, _f, sections, meta, chunks = _prepare()
    _e, full, _t, _c = _run(tmp_path, chunks, sections, meta, name='full')

    _e1, _partial, tfile, ckpt = _run(tmp_path, chunks[:5], sections, meta)
    with open(tfile, 'a', encoding='utf-8') as f:            # crash after the write, before the checkpoint
        f.write('<p>chunk six, translated but never checkpointed</p>\n')
    with open(ckpt, encoding='utf-8') as f:
        checkpoint = json.load(f)

    engine2 = TranslationEngine(tfile)
    engine2.restore_from_checkpoint(checkpoint)
    new = engine2.process_all_chunks(chunks[5:], sections, {}, tfile, ckpt, section_meta=meta)
    assert assemble_resume_content(new, 5, tfile) == full


def test_resume_refuses_when_the_output_file_lost_text(tmp_path):
    _body, _h, _f, sections, meta, chunks = _prepare()
    _e1, _partial, tfile, ckpt = _run(tmp_path, chunks[:5], sections, meta)
    with open(ckpt, encoding='utf-8') as f:
        checkpoint = json.load(f)
    os.remove(tfile)
    with pytest.raises(ValueError, match='missing'):
        TranslationEngine(tfile).restore_from_checkpoint(checkpoint)


def test_fresh_run_does_not_append_to_a_leftover_output_file(tmp_path):
    _body, _h, _f, sections, meta, chunks = _prepare()
    tfile = tmp_path / 'out_tmp.fb2'
    tfile.write_text('<section><p>leftover from an old run</p></section>\n', encoding='utf-8')
    _engine, content, tfile_path, _ckpt = _run(tmp_path, chunks, sections, meta)
    assert 'leftover' not in open(tfile_path, encoding='utf-8').read()


def test_without_section_meta_units_are_flat_sections(tmp_path):
    chunks = [{'chunk': '<p>a</p>', 'section_idx': 0, 'chunk_idx': 0, 'global_id': 0},
              {'chunk': '<p>b</p>', 'section_idx': 0, 'chunk_idx': 1, 'global_id': 1},
              {'chunk': '<p>c</p>', 'section_idx': 1, 'chunk_idx': 0, 'global_id': 2}]
    tfile = str(tmp_path / 't.fb2')
    content = TranslationEngine(tfile).process_all_chunks(chunks, [], {}, tfile)
    assert content == '<section>\n<p>a</p>\n<p>b</p>\n</section>\n<section>\n<p>c</p>\n</section>\n'


def test_trailing_units_without_text_are_still_emitted(tmp_path):
    meta = [{'open_tag': '<section id="a">', 'depth': 1}, {'open_tag': '<section id="e">', 'depth': 2}]
    chunks = [{'chunk': '<p>a</p>', 'section_idx': 0, 'chunk_idx': 0, 'global_id': 0}]
    tfile = str(tmp_path / 't.fb2')
    content = TranslationEngine(tfile).process_all_chunks(chunks, [[ '<p>a</p>'], []], {}, tfile, section_meta=meta)
    assert content == '<section id="a">\n<p>a</p>\n<section id="e">\n</section>\n</section>\n'


def test_a_cut_off_tail_is_closed_by_the_finalizer(tmp_path):
    _body, _h, _f, sections, meta, chunks = _prepare()
    _e, full, tfile, _c = _run(tmp_path, chunks, sections, meta)
    cut = full[:full.rindex('</section>')].rstrip('\n') + '\n'
    assert close_dangling_sections(cut) == full


# -- one translated chunk ------------------------------------------------

def test_llm_damage_is_repaired_inside_the_chunk():
    eng = TranslationEngine.__new__(TranslationEngine)
    assert eng._post_process_xml('src', '<p>one<p>two</p>\n\n\n<p>three</p></p>') == \
        '<p>one</p><p>two</p>\n\n<p>three</p>'
    assert eng._post_process_xml('src', 'no tags at all') == '<p>no tags at all</p>'
    assert eng._post_process_xml('src', '```xml\n<p>x</p>\n```') == '<p>x</p>'
    assert eng._post_process_xml('src', '<p>a</p></section><section><p>b</p>') == '<p>a</p><p>b</p>'


def test_failed_chunk_placeholder_is_a_valid_paragraph(monkeypatch):
    eng = TranslationEngine.__new__(TranslationEngine)
    eng.stats = {'successful': 0, 'failed': 0, 'retry_tokens': 0, 'total_tokens': 0}
    eng.translate_chunk = MagicMock(side_effect=RuntimeError('boom'))
    monkeypatch.setattr(app_module.time, 'sleep', lambda s: None)
    with patch.object(app_module, 'ta') as mock_ta:
        mock_ta.num_tokens_in_string.return_value = 1
        result, _syn = _REAL_PROCESS_CHUNK_RECURSIVE(eng, '<p>x</p>', 0, 0, 7, '')
    assert result == '<p>[TRANSLATION FAILED: chunk 7]</p>'
    assert eng.stats['failed'] == 1
