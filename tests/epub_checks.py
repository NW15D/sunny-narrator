"""Offline structural EPUB checks (epubcheck needs Java, which CI does not have)."""
import posixpath
import zipfile
from urllib.parse import unquote, urldefrag

from lxml import etree

from src import epub_writer
from src.fb2_handler import _read_file_with_encoding_fallback

XHTML = '{http://www.w3.org/1999/xhtml}'
OPF = '{http://www.idpf.org/2007/opf}'
EPUB_NS = 'http://www.idpf.org/2007/ops'
_NCNAME_START = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_')


def read_epub(path):
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist()}, zf.infolist()


def check_epub(path):
    """Return a list of problems (empty list = structurally sound)."""
    problems = []
    files, infos = read_epub(path)

    if infos[0].filename != 'mimetype' or infos[0].compress_type != zipfile.ZIP_STORED:
        problems.append('mimetype must be the first, stored entry')
    if files.get('mimetype') != b'application/epub+zip':
        problems.append('bad mimetype content')

    container = etree.fromstring(files['META-INF/container.xml'])
    opf_path = container.find('.//{*}rootfile').get('full-path')
    opf = etree.fromstring(files[opf_path])
    base = posixpath.dirname(opf_path)

    manifest = {}
    for item in opf.iterfind(f'.//{OPF}manifest/{OPF}item'):
        if item.get('id') in manifest:
            problems.append(f"duplicate manifest id {item.get('id')}")
        manifest[item.get('id')] = item
        target = posixpath.normpath(posixpath.join(base, unquote(item.get('href'))))
        if target not in files:
            problems.append(f"manifest href missing in zip: {item.get('href')}")
        if item.get('id')[0] not in _NCNAME_START:
            problems.append(f"manifest id is not an NCName: {item.get('id')}")

    for ref in opf.iterfind(f'.//{OPF}spine/{OPF}itemref'):
        if ref.get('idref') not in manifest:
            problems.append(f"spine idref not in manifest: {ref.get('idref')}")

    for tag in ('identifier', 'title', 'language'):
        if opf.find(f'.//{{http://purl.org/dc/elements/1.1/}}{tag}') is None:
            problems.append(f'missing dc:{tag}')
    ids = [e.get('id') for e in opf.iter() if e.get('id')]
    if len(ids) != len(set(ids)):
        problems.append(f'duplicate ids in OPF: {sorted({i for i in ids if ids.count(i) > 1})}')

    docs = {}
    for item in manifest.values():
        if item.get('media-type') == 'application/xhtml+xml':
            name = posixpath.normpath(posixpath.join(base, item.get('href')))
            try:
                docs[name] = etree.fromstring(files[name])
            except etree.XMLSyntaxError as e:
                problems.append(f'{name} is not well-formed: {e}')

    doc_ids = {}
    for name, root in docs.items():
        seen = [e.get('id') for e in root.iter() if e.get('id')]
        if len(seen) != len(set(seen)):
            problems.append(f'{name}: duplicate ids')
        doc_ids[name] = set(seen)

    for name, root in docs.items():
        for img in root.iter(f'{XHTML}img'):
            src = posixpath.normpath(posixpath.join(posixpath.dirname(name), img.get('src', '')))
            if src not in files:
                problems.append(f"{name}: img src not in zip: {img.get('src')}")
            if img.get('alt') is None:
                problems.append(f'{name}: img without alt')
        for a in root.iter(f'{XHTML}a'):
            href = a.get('href')
            if not href or href.startswith(('http:', 'https:', 'mailto:')):
                continue
            target, fragment = urldefrag(href)
            target = name if not target else posixpath.normpath(
                posixpath.join(posixpath.dirname(name), unquote(target)))
            if target not in docs:
                problems.append(f'{name}: link to unknown file {href}')
            elif fragment and fragment not in doc_ids[target]:
                problems.append(f'{name}: link to unknown id {href}')

    navs = [r for r in docs.values()
            if any(n.get(f'{{{EPUB_NS}}}type') == 'toc' for n in r.iter(f'{XHTML}nav'))]
    if not navs:
        problems.append('no nav document with epub:type="toc"')
    return problems


def fb2_file_to_epub(fb2_path, output_base):
    """Build an EPUB straight from an FB2 file (no translation)."""
    content = _read_file_with_encoding_fallback(fb2_path)
    start, end = content.find('<body'), content.find('</body>')
    header = content[:start]
    body = content[content.find('>', start) + 1:end]
    footer = content[end + len('</body>'):]
    return epub_writer.create_epub_from_fb2(header, body, footer, output_base)


def fragment_to_html(fragment, level=1, images=None):
    """Run the EPUB writer's FB2 -> XHTML conversion on a fragment."""
    soup, root = epub_writer._xml_soup(fragment)
    epub_writer._Converter(soup, images or {})._convert(root, level, [])
    out = []
    for child in root.children:
        epub_writer._serialize(child, out)
    return ''.join(out)
