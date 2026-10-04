"""D1: checkpoint and temp-file names must be deterministic (no timestamp)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app


def test_resume_paths_are_deterministic():
    p1 = app.build_resume_paths('/tmp/SomeBook.fb2', 'ru')
    p2 = app.build_resume_paths('/tmp/SomeBook.fb2', 'ru')
    assert p1['checkpoint_file'] == p2['checkpoint_file']
    assert p1['output_tfile'] == p2['output_tfile']
    assert p1['checkpoint_file'] == '/tmp/SomeBook_ru.checkpoint.json'
    assert p1['output_tfile'] == '/tmp/SomeBook_ru_tmp.fb2'


def test_resume_paths_have_no_timestamp():
    p = app.build_resume_paths('/tmp/SomeBook.fb2', 'ru')
    assert not re.search(r'\d{4}-\d{4}', p['checkpoint_file'])
    assert not re.search(r'\d{4}-\d{4}', p['output_tfile'])
    assert re.search(r'\d{4}-\d{4}', p['output_file'])


def test_language_marker_is_the_iso_code(tmp_path):
    # the same marker as the Calibre pipeline, whether TARGET_LANG is a name or a code
    book = str(tmp_path / 'SomeBook.fb2')
    for lang in ('russian', 'Russian', 'ru'):
        p = app.build_resume_paths(book, lang)
        assert p['checkpoint_file'] == str(tmp_path / 'SomeBook_ru.checkpoint.json')
        assert p['output_tfile'] == str(tmp_path / 'SomeBook_ru_tmp.fb2')
        assert os.path.basename(p['output_file']).startswith('SomeBook_ru_')


def test_checkpoint_under_the_old_name_is_resumed(tmp_path):
    book = str(tmp_path / 'SomeBook.fb2')
    (tmp_path / 'SomeBook_russian.checkpoint.json').write_text('{}')
    p = app.build_resume_paths(book, 'russian')
    assert p['checkpoint_file'] == str(tmp_path / 'SomeBook_russian.checkpoint.json')
    assert p['output_tfile'] == str(tmp_path / 'SomeBook_russian_tmp.fb2')
    assert os.path.basename(p['output_file']).startswith('SomeBook_ru_')
    # a checkpoint under the new name wins
    (tmp_path / 'SomeBook_ru.checkpoint.json').write_text('{}')
    assert app.build_resume_paths(book, 'russian')['checkpoint_file'] == \
        str(tmp_path / 'SomeBook_ru.checkpoint.json')
