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
