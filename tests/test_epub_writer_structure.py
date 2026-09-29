"""FB2 -> EPUB: section tree, links, notes, images, metadata."""
import os
import re
import sys
import zipfile

import pytest
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from epub_checks import EPUB_NS, XHTML, check_epub, fb2_file_to_epub, fragment_to_html
from src.epub_writer import create_epub_from_fb2

RICH = os.path.join(os.path.dirname(__file__), 'data', 'rich_book.fb2')
OPF_NS = '{http://www.idpf.org/2007/opf}'
DC = '{http://purl.org/dc/elements/1.1/}'


@pytest.fixture(scope='module')
def rich_epub(tmp_path_factory):
    return fb2_file_to_epub(RICH, str(tmp_path_factory.mktemp('epub') / 'rich'))


def _files(path):
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _chapter_texts(files):
    out = {}
    for name, data in files.items():
        if re.search(r'chapter_\d+\.xhtml$', name):
            root = etree.fromstring(data)
            out[name] = ' '.join(root.find(f'{XHTML}body').itertext())
    return out


def test_epub_is_structurally_sound(rich_epub):
    assert check_epub(rich_epub) == []


def test_every_paragraph_appears_exactly_once(rich_epub):
    text = ' '.join(_chapter_texts(_files(rich_epub)).values())
    for needle in ('Second chapter text.', 'Direct text only.', 'Tail of part one',
                   'Roses are red', 'And so are you', 'A quote.', 'First note.',
                   'Second note with', 'Part epigraph', 'Hello'):
        assert text.count(needle) == 1, needle


def test_toc_mirrors_the_section_tree(rich_epub):
    nav = etree.fromstring(_files(rich_epub)['EPUB/nav.xhtml'])
    toc = next(n for n in nav.iter(f'{XHTML}nav') if n.get(f'{{{EPUB_NS}}}type') == 'toc')

    def walk(ol):
        return [(li.find(f'{XHTML}a').text,
                 walk(li.find(f'{XHTML}ol')) if li.find(f'{XHTML}ol') is not None else [])
                for li in ol.findall(f'{XHTML}li')]

    assert walk(toc.find(f'{XHTML}ol')) == [
        ('The Rich Book', []),
        ('Part One', [('Chapter One', []), ('Chapter Two', [])]),
        ('Part Two', []),
        ('Notes', []),
    ]
    assert not [n for n in nav.iter(f'{XHTML}nav') if n.get(f'{{{EPUB_NS}}}type') == 'page-list']


def test_headings_follow_the_nesting_depth(rich_epub):
    files = _files(rich_epub)
    by_title = {}
    for name, data in files.items():
        if re.search(r'chapter_\d+\.xhtml$', name):
            root = etree.fromstring(data)
            for h in root.iter(*(f'{XHTML}h{i}' for i in range(1, 7))):
                label = ' '.join(t.strip() for t in h.itertext() if t.strip())
                by_title[label] = h.tag.rsplit('}', 1)[1]
    assert by_title['Part One'] == 'h1'
    assert by_title['Chapter One'] == 'h2' and by_title['Chapter Two'] == 'h2'


def test_notes_and_internal_links(rich_epub):
    files = _files(rich_epub)
    texts = _chapter_texts(files)
    chapter_one = next(n for n, t in texts.items() if 'Hello' in t)
    root = etree.fromstring(files[chapter_one])
    links = {a.text: a for a in root.iter(f'{XHTML}a')}
    assert links['[2]'].get(f'{{{EPUB_NS}}}type') == 'noteref'
    assert re.fullmatch(r'chapter_\d+\.xhtml#n2', links['[2]'].get('href'))
    assert re.fullmatch(r'chapter_\d+\.xhtml#c2', links['the next chapter'].get('href'))
    assert links['the web'].get('href') == 'http://example.com/x?a=1&b=2'
    notes = etree.fromstring(files['EPUB/' + links['[2]'].get('href').split('#')[0]])
    aside = next(a for a in notes.iter(f'{XHTML}aside') if a.get('id') == 'n2')
    assert aside.get(f'{{{EPUB_NS}}}type') == 'footnote'


def test_broken_internal_links_lose_the_link_but_keep_the_text(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    body = '<section><title><p>C</p></title><p>go <a l:href="#nowhere">there</a> now</p></section>'
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert check_epub(path) == []
    page = _files(path)['EPUB/chapter_0001.xhtml'].decode()
    assert 'go there now' in page and 'nowhere' not in page


def test_poem_title_is_a_block_not_an_empty_paragraph(rich_epub):
    page = next(d.decode() for n, d in _files(rich_epub).items() if b'Roses are red' in d)
    assert 'class="poem-title"' in page
    assert '<p class="title"/>' not in page and '<p class="title"></p>' not in page


def test_ids_that_are_not_valid_names_are_fixed(rich_epub):
    page = next(d.decode() for n, d in _files(rich_epub).items() if b'Direct text only.' in d)
    assert 'id="id_9lonely"' in page


def test_metadata_cover_and_series(rich_epub):
    files = _files(rich_epub)
    opf = etree.fromstring(files['EPUB/content.opf'])
    md = opf.find(f'{OPF_NS}metadata')
    creators = md.findall(f'{DC}creator')
    assert [c.text for c in creators] == ['Jane Q. Writer', 'Co-Author']
    assert len({c.get('id') for c in creators}) == 2
    assert md.find(f'{DC}identifier').text.startswith('urn:uuid:')
    assert md.find(f'{DC}language').text == 'en'
    assert md.find(f'{DC}title').text == 'The Rich Book & Its Parts'
    assert md.find(f'{DC}description').text == 'A test book. Second line.'
    metas = {m.get('name'): m.get('content') for m in md.findall(f'{OPF_NS}meta') if m.get('name')}
    assert metas['calibre:series'] == 'Test Series' and metas['calibre:series_index'] == '2'
    cover = next(i for i in opf.iterfind(f'.//{OPF_NS}item') if i.get('properties') == 'cover-image')
    assert cover.get('href') == 'images/cover.png'
    spine = [r.get('idref') for r in opf.iterfind(f'.//{OPF_NS}itemref')]
    assert spine[0] == 'cover'


def test_images_keep_alt_and_get_an_extension_from_their_content(tmp_path):
    import base64
    png = base64.b64encode(
        b'\x89PNG\r\n\x1a\n' + b'\x00' * 32).decode()
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    body = '<section><p>a <image l:href="#img1"/> b</p><image l:href="#img1"/><image l:href="#gone"/></section>'
    footer = f'<binary id="img1" content-type="image/jpg">{png}</binary>'
    path = create_epub_from_fb2(header, body, footer, str(tmp_path / 'b'))
    files = _files(path)
    assert 'EPUB/images/img1.png' in files
    assert check_epub(path) == []
    page = files['EPUB/chapter_0001.xhtml'].decode()
    assert page.count('<img') == 2 and 'gone' not in page


def test_epub_of_an_empty_body_is_refused(tmp_path):
    with pytest.raises(ValueError):
        create_epub_from_fb2('<description/>', '  ', '', str(tmp_path / 'b'))


def test_section_only_tree_without_titles_still_gets_a_toc(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>ru</lang></title-info></description>'
    body = '<section><p>один</p></section><section><p>два</p></section>'
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert check_epub(path) == []
    nav = etree.fromstring(_files(path)['EPUB/nav.xhtml'])
    assert len(list(nav.iter(f'{XHTML}li'))) == 2


def test_fb2_to_html_titles_and_poem_titles():
    out = fragment_to_html('<title><p>A</p><p>B</p></title><section><title><p>Sub</p></title></section>'
                       '<poem><title><p>PT</p></title><stanza><v>x</v></stanza></poem>')
    assert '<h1><span class="title-line">A</span><br/><span class="title-line">B</span></h1>' in out
    assert '<h2>' in out                              # title of a nested section
    assert '<div class="poem-title"><p>PT</p></div>' in out


def _page_texts(path):
    return {n: d.decode() for n, d in _files(path).items() if re.search(r'chapter_\d+\.xhtml$', n)}


def test_section_holding_only_subsections_gets_no_empty_page(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    body = ('<section><section><title><p>A</p></title><p>text a</p></section>'
            '<section><title><p>B</p></title><p>text b</p></section></section>')
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert check_epub(path) == []
    pages = _page_texts(path)
    assert len(pages) == 2
    nav = etree.fromstring(_files(path)['EPUB/nav.xhtml'])
    assert [a.text for a in nav.iter(f'{XHTML}a')] == ['A', 'B']


def test_style_unknown_tags_and_duplicate_ids(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    body = ('<section id="x"><p>a <style name="smallcaps">caps</style> <weird>kept text</weird></p>'
            '<p id="x">same id</p><p id="x y">bad id</p><!-- a comment --></section>')
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert check_epub(path) == []                      # includes the duplicate-id check
    page = next(iter(_page_texts(path).values()))
    assert '<span class="smallcaps">caps</span>' in page
    assert 'kept text' in page and '<weird' not in page
    assert 'a comment' not in page
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == len(set(ids)) == 3


def test_header_without_title_info_uses_defaults_and_publisher_is_kept(tmp_path):
    body = '<section><p>text</p></section>'
    path = create_epub_from_fb2('<description/>', body, '', str(tmp_path / 'a'))
    opf = _files(path)['EPUB/content.opf'].decode()
    assert '<dc:title>Unknown Title</dc:title>' in opf and '<dc:language>en</dc:language>' in opf

    header = ('<description><title-info><book-title>T</book-title><lang>en</lang></title-info>'
              '<publish-info><publisher>Pub &amp; Co</publisher></publish-info></description>')
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert '<dc:publisher>Pub &amp; Co</dc:publisher>' in _files(path)['EPUB/content.opf'].decode()


def test_body_without_readable_content_is_refused(tmp_path):
    with pytest.raises(ValueError, match='no readable content'):
        create_epub_from_fb2('<description/>', '<!-- only a comment -->', '', str(tmp_path / 'b'))


def test_untranslated_looking_body_is_only_a_warning(tmp_path, caplog):
    body = '<section><p>' + 'plain english words ' * 50 + '</p></section>'
    create_epub_from_fb2('<description/>', body, '', str(tmp_path / 'b'))
    assert 'High ASCII ratio' in caplog.text


def test_links_go_to_the_first_element_of_a_repeated_id(tmp_path):
    header = '<description><title-info><book-title>T</book-title><lang>en</lang></title-info></description>'
    body = ('<section><p id="dup">first</p><p id="dup">second</p>'
            '<p><a l:href="#dup">jump</a></p></section>')
    path = create_epub_from_fb2(header, body, '', str(tmp_path / 'b'))
    assert check_epub(path) == []
    page = next(iter(_page_texts(path).values()))
    assert '<p id="dup">first</p>' in page and 'href="#dup"' in page
