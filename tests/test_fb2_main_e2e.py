"""End-to-end: app.main() and the CLI on an FB2 book, with a fake LLM.

The fake "translation" upper-cases text and, every few chunks, damages the
markup the way LLMs do (a lost </p>, a code fence), so the whole classic path
runs: chunking, local repair, section tree, metadata, validation, auto-repair,
FB2/EPUB writing, checkpoint and resume.
"""
import glob
import json
import os
import re
import runpy
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

import app
import src.utils as utils
import src.xmlcheck as xc
from epub_checks import check_epub

ROOT = os.path.join(os.path.dirname(__file__), '..')
RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
TAIL = '<p>Tail of part one after its sections (odd but seen in the wild).</p>\n'


class Interrupted(BaseException):
    """Escapes the per-chunk retry loop (which catches Exception), like Ctrl+C."""


def _fake_translate(fail_on=None):
    calls = {'n': 0}

    def translate(source_lang, target_lang, source_text, outline_text, vocab_dict,
                  vocab_entries=None, country='', style='text', fast_mode=False,
                  depth=0, _llm_call_count=None, candidate_sink=None):
        calls['n'] += 1
        if fail_on is not None and calls['n'] == fail_on:
            raise Interrupted
        out = re.sub(r'>([^<]+)<', lambda m: '>' + m.group(1).upper() + '<', source_text)
        if calls['n'] % 3 == 0:
            out = out.replace('</p>', '', 1)
        if calls['n'] % 4 == 0:
            out = '```xml\n' + out + '\n```'
        return out, ''
    return translate


def _fake_metadata(metadata, *args, **kwargs):
    return dict(metadata, **{'book-title': 'БОГАТАЯ КНИГА'})


@pytest.fixture
def book(tmp_path):
    """A schema-valid copy of the rich fixture plus an (empty) reviewed dictionary."""
    with open(RICH, encoding='cp1251') as f:
        text = f.read().replace(TAIL, '').replace('9lonely', 'lonely')
    path = tmp_path / 'book.fb2'
    path.write_text(text, encoding='cp1251')
    (tmp_path / 'book.dic').write_text('# reviewed, no terms\n', encoding='utf-8')
    return path


@pytest.fixture(autouse=True)
def _restore_signal_handlers():
    """main() installs its own SIGINT/SIGTERM handlers; keep pytest's."""
    import signal
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


@pytest.fixture
def run_main(monkeypatch):
    def run(book_path, output_format='fb2', translate=None, metadata=_fake_metadata,
            max_len=300, images_key=''):
        monkeypatch.setattr(app.config, 'myfile', str(book_path))
        monkeypatch.setattr(app.config, 'output_format', output_format)
        monkeypatch.setattr(app.config, 'ner_opt', False)
        monkeypatch.setattr(app.config, 'api_key_images', images_key)
        monkeypatch.setattr(app.config, 'max_len_chunk', max_len)
        monkeypatch.setattr(app.config, 'dictionary', None)
        monkeypatch.setattr(app.config, 'fb2_auto_repair', True)
        monkeypatch.setattr(app.ta, 'translate_chunk', translate or _fake_translate())
        monkeypatch.setattr(app.ta, 'translate_metadata', metadata)
        monkeypatch.setattr(app.time, 'sleep', lambda s: None)
        app.main()
    return run


def _outputs(folder, ext):
    return [p for p in glob.glob(os.path.join(folder, f'book_russian_*.{ext}'))
            if not p.endswith('_tmp.fb2')]


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_fb2_to_fb2(book, run_main):
    run_main(book)
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)

    assert xc.validate_fb2(xml) == []
    assert xml.lower().startswith('<?xml version="1.0" encoding="utf-8"?>')  # source was cp1251
    for needle in ('ROSES ARE RED', 'SECOND CHAPTER TEXT.', 'DIRECT TEXT ONLY.', 'PART EPIGRAPH',
                   '<section id="part1">', '<section id="c1">', '<section id="lonely">',
                   '<book-title>БОГАТАЯ КНИГА</book-title>', '<lang>ru</lang><src-lang>en</src-lang>',
                   '<body name="notes">', 'First note.', '<binary id="cover.png"'):
        assert needle in xml, needle
    assert '```' not in xml and '[TRANSLATION FAILED' not in xml
    assert not glob.glob(os.path.join(book.parent, '*.checkpoint.json'))
    assert not _outputs(book.parent, 'epub')


def test_fb2_to_epub(book, run_main):
    run_main(book, output_format='epub')
    [out] = _outputs(book.parent, 'epub')
    assert check_epub(out) == []
    import zipfile
    with zipfile.ZipFile(out) as zf:
        pages = ' '.join(zf.read(n).decode() for n in zf.namelist() if n.endswith('.xhtml'))
        opf = zf.read('EPUB/content.opf').decode()
    assert 'ROSES ARE RED' in pages and 'DIRECT TEXT ONLY.' in pages
    assert '<dc:title>БОГАТАЯ КНИГА</dc:title>' in opf and '<dc:language>ru</dc:language>' in opf
    assert not _outputs(book.parent, 'fb2')


def test_epub_failure_falls_back_to_fb2(book, run_main, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('ebooklib exploded')
    monkeypatch.setattr(app, 'create_epub_from_fb2', boom)
    run_main(book, output_format='epub')
    [out] = _outputs(book.parent, 'fb2')
    assert xc.validate_fb2(_read(out)) == []
    assert not _outputs(book.parent, 'epub')


def test_validation_errors_are_handed_to_the_auto_repair(book, run_main, monkeypatch):
    book.write_text(book.read_text(encoding='cp1251').replace('id="lonely"', 'id="9lonely"'),
                    encoding='cp1251')
    seen = {}
    real = app.write_to_file

    def spy(data, output_file, auto_repair_fb2=False, known_errors=None):
        seen.update(auto_repair=auto_repair_fb2, errors=known_errors)
        return real(data, output_file, auto_repair_fb2=auto_repair_fb2, known_errors=known_errors)

    monkeypatch.setattr(app, 'write_to_file', spy)
    run_main(book)
    assert seen['auto_repair'] is True
    assert seen['errors'] and "'9lonely'" in seen['errors'][0]


def test_interrupted_run_resumes_to_the_same_book(book, run_main, tmp_path):
    reference = tmp_path / 'reference'
    reference.mkdir()
    shutil.copy(book, reference / 'book.fb2')
    shutil.copy(book.parent / 'book.dic', reference / 'book.dic')
    run_main(reference / 'book.fb2')
    [expected] = _outputs(reference, 'fb2')

    with pytest.raises(Interrupted):
        run_main(book, translate=_fake_translate(fail_on=5))
    assert glob.glob(os.path.join(book.parent, '*.checkpoint.json'))
    assert not _outputs(book.parent, 'fb2')

    # The fake counts calls; a resumed run must damage the same chunks the same
    # way as the reference run did, so it starts counting where run 1 stopped.
    translate = _fake_translate()
    for _ in range(4):
        translate('en', 'ru', '<p>x</p>', '', {})
    run_main(book, translate=translate)

    [out] = _outputs(book.parent, 'fb2')
    body = re.search(r'<body>.*?</body>', _read(out), re.DOTALL).group(0)
    assert body == re.search(r'<body>.*?</body>', _read(expected), re.DOTALL).group(0)
    assert not glob.glob(os.path.join(book.parent, '*.checkpoint.json'))


def test_resume_when_every_chunk_was_already_translated(book, run_main, tmp_path):
    def interrupted_metadata(metadata, *args, **kwargs):
        raise Interrupted

    with pytest.raises(Interrupted):
        run_main(book, metadata=interrupted_metadata)
    assert glob.glob(os.path.join(book.parent, '*.checkpoint.json'))

    def no_llm(*args, **kwargs):
        raise AssertionError('nothing is left to translate')

    run_main(book, translate=no_llm)
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert xc.validate_fb2(xml) == []
    assert 'ROSES ARE RED' in xml and 'DIRECT TEXT ONLY.' in xml


# --------------------------------------------------------------------------
# CLI: python app.py [--output-format ...] on an FB2 input
# --------------------------------------------------------------------------

@pytest.fixture
def run_cli(monkeypatch):
    def run(book_path, *argv, env_format='fb2'):
        monkeypatch.setenv('FILE', str(book_path))
        monkeypatch.setenv('NER', 'False')
        monkeypatch.setenv('API_KEY_IMAGES', '')
        monkeypatch.setenv('MAX_LEN_CHUNK', '300')
        monkeypatch.setenv('OUTPUT_FORMAT', env_format)
        monkeypatch.delenv('DICTIONARY', raising=False)
        monkeypatch.setattr(utils, 'translate_chunk', _fake_translate())
        monkeypatch.setattr(utils, 'translate_metadata', _fake_metadata)
        monkeypatch.setattr(sys, 'argv', ['app.py', *argv])
        runpy.run_path(os.path.join(ROOT, 'app.py'), run_name='__main__')
    return run


def test_cli_output_format_epub_reaches_the_classic_pipeline(book, run_cli):
    run_cli(book, '--output-format', 'epub')
    [out] = _outputs(book.parent, 'epub')
    assert check_epub(out) == []
    assert not _outputs(book.parent, 'fb2')


def test_cli_flag_overrides_the_env_format(book, run_cli):
    run_cli(book, '--output-format', 'fb2', env_format='epub')
    assert _outputs(book.parent, 'fb2') and not _outputs(book.parent, 'epub')


def test_env_format_is_used_without_the_flag(book, run_cli):
    run_cli(book, env_format='epub')
    assert _outputs(book.parent, 'epub') and not _outputs(book.parent, 'fb2')


def test_cli_rejects_a_format_fb2_cannot_be_written_as(book, run_cli, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(book, '--output-format', 'docx')
    assert exc.value.code == 1
    assert 'fb2 or epub' in capsys.readouterr().out
    assert not _outputs(book.parent, 'fb2') and not _outputs(book.parent, 'epub')


def test_stale_checkpoint_is_ignored_and_the_book_is_translated_from_scratch(book, run_main):
    with pytest.raises(Interrupted):
        run_main(book, translate=_fake_translate(fail_on=5))
    # A different chunk size slices the book differently: the checkpoint no longer applies.
    run_main(book, max_len=120)
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert xc.validate_fb2(xml) == []
    assert xml.count('ROSES ARE RED') == 1 and xml.count('DIRECT TEXT ONLY.') == 1


def test_lost_translation_file_restarts_instead_of_resuming_into_a_hole(book, run_main):
    with pytest.raises(Interrupted):
        run_main(book, translate=_fake_translate(fail_on=5))
    [tfile] = glob.glob(os.path.join(book.parent, '*_tmp.fb2'))
    os.remove(tfile)

    run_main(book)
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert xc.validate_fb2(xml) == []
    for needle in ('THE RICH BOOK', 'HELLO', 'ROSES ARE RED', 'DIRECT TEXT ONLY.'):
        assert xml.count(needle) == 1, needle


@pytest.mark.parametrize('image, content_type, ext', [
    (b'\x89PNG\r\n\x1a\n' + b'\x00' * 24, 'image/png', 'png'),
    (b'\xff\xd8\xff\xe0' + b'\x00' * 24, 'image/jpeg', 'jpg'),
])
def test_cover_is_sent_to_the_image_model_and_replaced(book, run_main, monkeypatch, image, content_type, ext):
    import base64
    new_cover = base64.b64encode(image).decode()
    sent = []

    def fake_image(image_data, source_lang, target_lang, country, metadata=None):
        sent.append(image_data)
        return new_cover

    monkeypatch.setattr(app.ta, 'process_image_request', fake_image)
    run_main(book, images_key='key')

    assert len(sent) == 1 and isinstance(sent[0], str)   # the cover's base64, not a (href, data) tuple
    base64.b64decode(sent[0])
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert f'<binary content-type="{content_type}" id="cover.png">{new_cover}</binary>' in xml
    assert xc.validate_fb2(xml) == []
    saved = sorted(p.name for p in book.parent.glob('book_*cover.*'))
    assert saved == [f'book_russian_cover.{ext}']
    assert (book.parent / saved[0]).read_bytes() == image


def test_book_without_a_cover_does_not_call_the_image_model(book, run_main, monkeypatch):
    text = book.read_text(encoding='cp1251')
    book.write_text(text.replace('<coverpage><image l:href="#cover.png"/></coverpage>\n', ''), encoding='cp1251')

    def no_image_model(*args, **kwargs):
        raise AssertionError('there is no cover to send')

    monkeypatch.setattr(app.ta, 'process_image_request', no_image_model)
    run_main(book, images_key='key')
    assert _outputs(book.parent, 'fb2')


def test_unknown_arguments_are_reported(book, run_cli, capsys):
    run_cli(book, '--pipeline', 'classic')
    assert 'ignoring unknown arguments: --pipeline classic' in capsys.readouterr().out
    assert _outputs(book.parent, 'fb2')


def test_checkpoint_of_a_different_section_tree_is_not_resumed(book, run_main, capsys):
    with pytest.raises(Interrupted):
        run_main(book, translate=_fake_translate(fail_on=5))
    # Same text and same chunks, but chapter two now sits at the top level.
    text = book.read_text(encoding='cp1251')
    moved = re.search(r'<section id="c2">.*?</section>\n', text, re.DOTALL).group(0)
    text = text.replace(moved, '', 1).replace('<section id="lonely">', moved + '<section id="lonely">', 1)
    book.write_text(text, encoding='cp1251')

    run_main(book)
    assert 'Checkpoint ignored' in capsys.readouterr().out
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert xc.validate_fb2(xml) == []
    assert xml.count('SECOND CHAPTER TEXT.') == 1


def test_old_version_checkpoints_are_not_resumed():
    from src.checkpoint_manager import CHECKPOINT_VERSION, compute_fingerprint
    assert CHECKPOINT_VERSION >= 3
    chunks = ['<p>a</p>']
    assert compute_fingerprint(chunks, section_tree='[]') != compute_fingerprint(chunks, section_tree='[[1]]')


@pytest.mark.parametrize('llm_lang', ['русский', ['Russian'], None])
def test_book_language_comes_from_the_config_not_the_llm(book, run_main, llm_lang):
    def metadata_llm(metadata, *args, **kwargs):
        answer = dict(metadata, **{'book-title': 'БОГАТАЯ КНИГА'})
        if llm_lang is None:
            answer.pop('lang')
        else:
            answer['lang'] = llm_lang
        return answer

    run_main(book, output_format='epub', metadata=metadata_llm)
    [out] = _outputs(book.parent, 'epub')
    import zipfile
    with zipfile.ZipFile(out) as zf:
        assert '<dc:language>ru</dc:language>' in zf.read('EPUB/content.opf').decode()


def test_fb2_language_comes_from_the_config_not_the_llm(book, run_main):
    run_main(book, metadata=lambda metadata, *a, **k: dict(metadata, lang='русский'))
    [out] = _outputs(book.parent, 'fb2')
    xml = _read(out)
    assert '<lang>ru</lang>' in xml and xc.validate_fb2(xml) == []


def test_main_on_its_own_never_writes_fb2_into_a_pdf(book, run_main):
    run_main(book, output_format='pdf')
    assert _outputs(book.parent, 'fb2')
    assert not glob.glob(os.path.join(book.parent, 'book_russian_*.pdf'))


def test_covers_of_different_target_languages_do_not_overwrite_each_other(book, run_main, monkeypatch):
    import base64
    png = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 24).decode()
    monkeypatch.setattr(app.ta, 'process_image_request', lambda *a, **k: png)
    run_main(book, images_key='key')
    monkeypatch.setattr(app.config, 'target_lang', 'german')
    run_main(book, images_key='key')
    names = sorted(p.name for p in book.parent.glob('book_*cover.*'))
    assert names == ['book_german_cover.png', 'book_russian_cover.png']



def test_sigterm_saves_a_checkpoint_and_the_run_resumes(book, run_main, tmp_path):
    import signal
    reference = tmp_path / 'reference'
    reference.mkdir()
    shutil.copy(book, reference / 'book.fb2')
    shutil.copy(book.parent / 'book.dic', reference / 'book.dic')
    run_main(reference / 'book.fb2')
    [expected] = _outputs(reference, 'fb2')

    base = _fake_translate()
    calls = {'n': 0}

    def translate_then_sigterm(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 5:
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)   # what the OS would call
        return base(*args, **kwargs)

    with pytest.raises(SystemExit) as exc:
        run_main(book, translate=translate_then_sigterm)
    assert exc.value.code == 1
    [ckpt] = glob.glob(os.path.join(book.parent, '*.checkpoint.json'))
    with open(ckpt, encoding='utf-8') as f:
        assert json.load(f)['last_chunk'] == 3                    # chunks 0-3 finished

    translate = _fake_translate()
    for _ in range(4):
        translate('en', 'ru', '<p>x</p>', '', {})
    run_main(book, translate=translate)
    [out] = _outputs(book.parent, 'fb2')
    body = re.search(r'<body>.*?</body>', _read(out), re.DOTALL).group(0)
    assert body == re.search(r'<body>.*?</body>', _read(expected), re.DOTALL).group(0)


def test_first_run_creates_the_dictionary_and_stops(book, run_main, monkeypatch):
    import src.vocabulary_manager as vm
    monkeypatch.setattr(vm.config, 'ner_opt', False)   # no spaCy model in the test env: empty template
    os.remove(book.parent / 'book.dic')

    def no_llm(*args, **kwargs):
        raise AssertionError('nothing is translated before the dictionary is reviewed')

    with pytest.raises(SystemExit) as exc:
        run_main(book, translate=no_llm)
    assert exc.value.code == 0
    assert (book.parent / 'book.dic').exists()
    assert not _outputs(book.parent, 'fb2') and not _outputs(book.parent, 'epub')
