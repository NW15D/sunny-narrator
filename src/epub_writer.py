"""
EPUB Writer

Creates EPUB files from the FB2 representation the classic pipeline produces
(header / body / footer strings).

Every FB2 <section> becomes an XHTML file (a section that has sub-sections gets
one file for its own text and one per sub-section, so no text is repeated), the
table of contents mirrors the section tree, footnote bodies become a "Notes"
file and internal <a> links are rewritten to file#id targets.
"""

import base64
import html
import logging
import re
import uuid
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from ebooklib import epub

from src.config import Config
from src.xml_utils import IMAGE_EXTENSIONS, sniff_image_type

config = Config()
logger = logging.getLogger(__name__)

_XLINK_NS = 'xmlns:l="http://www.w3.org/1999/xlink" xmlns:xlink="http://www.w3.org/1999/xlink"'
_HTML_VOID = {'br', 'img', 'hr'}
_INLINE_NAMES = {'p', 'v', 'subtitle', 'text-author', 'td', 'th', 'strong', 'emphasis',
                 'em', 'a', 'span', 's', 'strikethrough', 'sub', 'sup', 'code', 'style',
                 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

# FB2 element -> (HTML element, class)
_SIMPLE = {
    'emphasis': ('em', None),
    'strikethrough': ('s', None),
    'cite': ('blockquote', 'cite'),
    'epigraph': ('blockquote', 'epigraph'),
    'poem': ('div', 'poem'),
    'stanza': ('div', 'stanza'),
    'v': ('p', 'verse'),
    'text-author': ('p', 'text-author'),
    'date': ('p', 'date'),
    'subtitle': ('p', 'subtitle'),
    'annotation': ('div', 'annotation'),
    'history': ('div', 'history'),
}
_KEEP = {'p', 'strong', 'sub', 'sup', 'code', 'em', 's', 'table', 'tr', 'th', 'td',
         'section', 'aside', 'div', 'blockquote', 'span', 'br', 'img', 'a',
         'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'root'}
_PLAIN_ATTRS = {'class', 'xml:lang', 'colspan', 'rowspan', 'src', 'alt', 'href', 'epub:type', 'title'}
_ALIGN_CSS = {'align': 'text-align', 'valign': 'vertical-align'}

_CSS = """\
body { margin: 0 5%; line-height: 1.4; }
p { margin: 0; text-indent: 1.5em; text-align: justify; }
h1, h2, h3, h4, h5, h6 { text-align: center; margin: 1.6em 0 1em; line-height: 1.25; page-break-after: avoid; }
h1 { font-size: 1.6em; }
h2 { font-size: 1.35em; }
h3 { font-size: 1.15em; }
.subtitle { text-align: center; font-weight: bold; text-indent: 0; margin: 1.2em 0 0.8em; }
.epigraph { margin: 1em 0 1em 25%; font-style: italic; }
.cite { margin: 1em 2em; }
.text-author { text-align: right; font-style: italic; text-indent: 0; }
.date { text-align: right; text-indent: 0; }
.poem { margin: 1em 0 1em 2em; }
.stanza { margin: 0 0 1em; }
.verse { text-indent: 0; text-align: left; }
.poem-title, .title { font-weight: bold; text-align: center; }
.poem-title p, .title p { text-indent: 0; text-align: center; }
.image { text-align: center; margin: 1em 0; }
.image img, p img { max-width: 100%; height: auto; }
table { border-collapse: collapse; margin: 1em auto; }
td, th { border: 1px solid #888; padding: 0.25em 0.5em; text-indent: 0; }
a.noteref { vertical-align: super; font-size: 0.75em; text-decoration: none; }
aside { margin: 0.6em 0; }
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _href(tag: Tag) -> str:
    return tag.get('l:href') or tag.get('xlink:href') or tag.get('href') or ''


def _text(tag: Optional[Tag]) -> str:
    return re.sub(r'\s+', ' ', tag.get_text(' ', strip=True)).strip() if tag is not None else ''


def _xml_soup(fragment: str) -> Tuple[BeautifulSoup, Tag]:
    soup = BeautifulSoup(f'<root {_XLINK_NS}>{fragment}</root>', 'xml')
    return soup, soup.find('root')


def _serialize(node, out: List[str]) -> None:
    """Serialize as HTML-parser-safe XHTML (no self-closed non-void elements)."""
    if isinstance(node, Comment):
        return
    if isinstance(node, NavigableString):
        out.append(html.escape(str(node), quote=False))
        return
    attrs = ''.join(
        f' {k}="{html.escape(" ".join(v) if isinstance(v, list) else str(v), quote=True)}"'
        for k, v in node.attrs.items())
    if node.name in _HTML_VOID:
        out.append(f'<{node.name}{attrs}/>')
        return
    out.append(f'<{node.name}{attrs}>')
    for child in node.children:
        _serialize(child, out)
    out.append(f'</{node.name}>')


def _load_images(footer: str) -> Dict[str, dict]:
    """FB2 <binary> blocks -> {fb2 id: {data, content_type, file_name, uid}}."""
    images: Dict[str, dict] = {}
    used_names = set()
    for m in re.finditer(r'<binary\b([^>]*)>(.*?)</binary>', footer, re.DOTALL):
        attrs = {k.lower(): v for k, v in re.findall(r'([\w:-]+)\s*=\s*["\']([^"\']*)["\']', m.group(1))}
        image_id = attrs.get('id')
        if not image_id:
            continue
        try:
            data = base64.b64decode(re.sub(r'\s+', '', m.group(2)))
        except Exception as e:
            logger.warning(f"Skipping image {image_id}: bad base64 ({e})")
            continue
        content_type = sniff_image_type(data, attrs.get('content-type', ''))
        if not content_type:
            continue
        ext = IMAGE_EXTENSIONS[content_type]
        base = re.sub(r'[^A-Za-z0-9_.-]', '_', image_id) or 'image'
        if not (base.lower().endswith(ext) or (ext == '.jpg' and base.lower().endswith('.jpeg'))):
            base += ext
        name, n = base, 1
        while name.lower() in used_names:
            n += 1
            name = f'{base.rsplit(".", 1)[0]}_{n}{ext}'
        used_names.add(name.lower())
        images[image_id] = {'data': data, 'content_type': content_type,
                            'file_name': f'images/{name}', 'uid': f'img{len(images) + 1}'}
    return images


def _parse_metadata(header: str) -> dict:
    soup = BeautifulSoup(header, 'xml')
    info = soup.find('title-info')
    meta = {'title': 'Unknown Title', 'authors': [], 'lang': 'en', 'description': '',
            'genres': [], 'series': None, 'publisher': '', 'cover_id': None}
    if info is None:
        return meta

    title = _text(info.find('book-title'))
    if title:
        meta['title'] = title

    for author in info.find_all('author', recursive=False):
        parts = [_text(author.find(n)) for n in ('first-name', 'middle-name', 'last-name')]
        name = ' '.join(p for p in parts if p) or _text(author.find('nickname'))
        if name:
            meta['authors'].append(name)

    lang = _text(info.find('lang')).replace('_', '-')
    if lang:
        meta['lang'] = lang

    annotation = info.find('annotation')
    if annotation is not None:
        paragraphs = [_text(p) for p in annotation.find_all('p')]
        meta['description'] = ' '.join(p for p in paragraphs if p) or _text(annotation)

    meta['genres'] = [_text(g) for g in info.find_all('genre') if _text(g)]

    sequence = info.find('sequence')
    if sequence is not None and sequence.get('name'):
        meta['series'] = (sequence.get('name'), sequence.get('number', ''))

    publisher = soup.find('publish-info')
    if publisher is not None:
        meta['publisher'] = _text(publisher.find('publisher'))

    cover = info.find('coverpage')
    image = cover.find('image') if cover is not None else None
    if image is not None and _href(image).startswith('#'):
        meta['cover_id'] = _href(image)[1:]
    return meta


def _extra_bodies(footer: str) -> List[str]:
    """Inner XML of every <body> in the footer (footnotes, comments)."""
    return [m.group(1) for m in re.finditer(r'<body\b[^>]*>(.*?)</body>', footer, re.DOTALL)]


# ---------------------------------------------------------------------------
# Body -> XHTML pages
# ---------------------------------------------------------------------------

class _Page:
    def __init__(self, file_name: str, title: str, wrapper: Tag, links: List[Tag]):
        self.file_name = file_name
        self.title = title
        self.wrapper = wrapper
        self.links = links


class _Converter:
    """Turns an FB2 body (bs4 tree) into XHTML pages plus a nested TOC."""

    def __init__(self, soup: BeautifulSoup, images: Dict[str, dict]):
        self.soup = soup
        self.images = images
        self.pages: List[_Page] = []
        self._aliases: Dict[str, str] = {}
        self._used_ids: set = set()
        self._id_file: Dict[str, str] = {}
        self._untitled = 0

    # -- ids ---------------------------------------------------------------
    def alias(self, old: str) -> str:
        """XHTML id for an FB2 id. The first element with that id owns it
        (links resolve to it); a repeated id in a broken FB2 gets a fresh,
        unlinked one, since XHTML ids must be unique."""
        if old in self._aliases:
            return self._fresh_id(old)
        new = self._fresh_id(old)
        self._aliases[old] = new
        return new

    def _fresh_id(self, old: str) -> str:
        new = re.sub(r'[^A-Za-z0-9_.-]', '_', old) or 'id'
        if not re.match(r'[A-Za-z_]', new):
            new = f'id_{new}'
        base, n = new, 1
        while new in self._used_ids:
            n += 1
            new = f'{base}_{n}'
        self._used_ids.add(new)
        return new

    # -- tree walk ---------------------------------------------------------
    @staticmethod
    def _has_content(nodes: list) -> bool:
        return any(isinstance(n, Tag) or (isinstance(n, NavigableString)
                                          and not isinstance(n, Comment) and str(n).strip())
                   for n in nodes)

    def _fallback_title(self) -> str:
        self._untitled += 1
        return str(self._untitled)

    def _new_page(self, nodes: list, title: str, level: int, section_id: Optional[str]) -> _Page:
        wrapper = self.soup.new_tag('section')
        if section_id:
            wrapper['id'] = section_id
        for node in nodes:
            wrapper.append(node.extract())
        links: List[Tag] = []
        self._convert(wrapper, level, links)
        file_name = f'chapter_{len(self.pages) + 1:04d}.xhtml'
        for t in [wrapper, *wrapper.find_all(id=True)]:
            if t.get('id'):
                self._id_file[t['id']] = file_name
        page = _Page(file_name, title, wrapper, links)
        self.pages.append(page)
        return page

    def _walk_section(self, section: Tag, level: int) -> list:
        """Return TOC nodes [(file, title, [children])] for this section."""
        title = _text(section.find('title', recursive=False))
        title_for_page = title or self._fallback_title()
        nodes: list = []
        first: Optional[_Page] = None
        children: list = []

        def flush():
            nonlocal nodes, first
            if self._has_content(nodes):
                page = self._new_page(nodes, title_for_page, level,
                                      section.get('id') and self.alias(section['id']) if first is None else None)
                first = first or page
            nodes = []

        for child in list(section.children):
            if isinstance(child, Tag) and child.name == 'section':
                flush()
                children.extend(self._walk_section(child, level + 1))
            else:
                nodes.append(child)
        flush()
        if first is None:
            return children
        return [(first.file_name, title_for_page, children)]

    def build(self, body_root: Tag, extra_roots: List[Tag]) -> list:
        toc: list = []
        nodes: list = []

        def flush_front():
            nonlocal nodes
            if self._has_content(nodes):
                page = self._new_page(nodes, _text(next((n for n in nodes if isinstance(n, Tag)
                                                         and n.name == 'title'), None))
                                      or self._fallback_title(), 1, None)
                toc.append((page.file_name, page.title, []))
            nodes = []

        for child in list(body_root.children):
            if isinstance(child, Tag) and child.name == 'section':
                flush_front()
                toc.extend(self._walk_section(child, 1))
            else:
                nodes.append(child)
        flush_front()

        for root in extra_roots:
            title = _text(root.find('title', recursive=False)) or 'Notes'
            notes_nodes = []
            for child in list(root.children):
                if isinstance(child, Tag) and child.name == 'section':
                    child.name = 'aside'
                    child['epub:type'] = 'footnote'
                notes_nodes.append(child)
            if self._has_content(notes_nodes):
                page = self._new_page(notes_nodes, title, 1, None)
                toc.append((page.file_name, title, []))

        self._resolve_links()
        return toc

    # -- element conversion ------------------------------------------------
    def _title_level(self, tag: Tag, wrapper: Tag, base: int) -> Optional[int]:
        parent = tag.parent
        if parent is wrapper:
            return base
        if parent is not None and parent.name == 'section':
            depth, p = 0, parent
            while p is not None and p is not wrapper:
                depth += p.name == 'section'
                p = p.parent
            return base + depth
        return None

    def _convert(self, wrapper: Tag, level: int, links: List[Tag]) -> None:
        soup = self.soup
        for tag in list(wrapper.find_all(True)):
            if getattr(tag, 'decomposed', False):
                continue
            name = tag.name
            classes = [tag['class']] if tag.get('class') else []

            if name == 'title':
                lvl = self._title_level(tag, wrapper, level)
                if lvl is not None:
                    tag.name = f'h{min(lvl, 6)}'
                    for i, p in enumerate(tag.find_all('p', recursive=False)):
                        if i:
                            p.insert_before(soup.new_tag('br'))
                        p.name = 'span'
                        p['class'] = 'title-line'
                else:
                    tag.name = 'div'
                    parent_classes = (tag.parent.get('class') or '').split() if tag.parent is not None else []
                    in_poem = bool({'poem', 'stanza'} & set(parent_classes))
                    classes.append('poem-title' if in_poem else 'title')
            elif name in _SIMPLE:
                tag.name, cls = _SIMPLE[name]
                if cls:
                    classes.append(cls)
            elif name == 'empty-line':
                tag.name = 'br'
                tag.attrs = {}
                continue
            elif name == 'style':
                tag.name = 'span'
                if tag.get('name'):
                    classes.append(tag['name'])
            elif name == 'image':
                self._convert_image(tag)
                continue
            elif name == 'a':
                if not self._convert_link(tag, links):
                    continue
            elif name not in _KEEP:
                tag.unwrap()
                continue

            self._clean_attrs(tag, classes)

    def _convert_image(self, tag: Tag) -> None:
        href = _href(tag)
        info = self.images.get(href[1:]) if href.startswith('#') else None
        if info is None:  # no such <binary>: an image that would not load
            tag.decompose()
            return
        img = self.soup.new_tag('img')
        img['src'] = info['file_name']
        img['alt'] = tag.get('alt') or tag.get('title') or ''
        parent = tag.parent
        if parent is not None and parent.name in _INLINE_NAMES:
            tag.replace_with(img)
        else:
            block = self.soup.new_tag('div')
            block['class'] = 'image'
            block.append(img)
            tag.replace_with(block)

    def _convert_link(self, tag: Tag, links: List[Tag]) -> bool:
        href = _href(tag)
        if not href:
            tag.unwrap()
            return False
        kind = tag.get('type')
        tag.attrs = {'href': href}
        if kind == 'note':
            tag['epub:type'] = 'noteref'
            tag['class'] = 'noteref'
        if href.startswith('#'):
            links.append(tag)
        return True

    def _clean_attrs(self, tag: Tag, classes: List[str]) -> None:
        attrs: Dict[str, str] = {}
        css: List[str] = []
        for key, value in tag.attrs.items():
            if key == 'id':
                attrs['id'] = self.alias(value)
            elif key == 'style':
                classes.append(value)
            elif key in _ALIGN_CSS:
                css.append(f'{_ALIGN_CSS[key]}: {value}')
            elif key in _PLAIN_ATTRS:
                attrs[key] = value
        if attrs.get('class') and attrs['class'] not in classes:
            classes.insert(0, attrs['class'])
        classes = [c for c in dict.fromkeys(classes) if c]
        if classes:
            attrs['class'] = ' '.join(classes)
        else:
            attrs.pop('class', None)
        if css:
            attrs['style'] = '; '.join(css)
        tag.attrs = attrs

    def _resolve_links(self) -> None:
        for page in self.pages:
            for a in page.links:
                if getattr(a, 'decomposed', False):
                    continue
                old = a['href'][1:]
                target = self._aliases.get(old)
                file_name = self._id_file.get(target) if target else None
                if file_name is None:
                    a.unwrap()
                else:
                    a['href'] = f'#{target}' if file_name == page.file_name else f'{file_name}#{target}'

    def page_html(self, page: _Page) -> str:
        out: List[str] = []
        _serialize(page.wrapper, out)
        return f'<html><body>{"".join(out)}</body></html>'


def _toc_items(nodes: list, counter: List[int]) -> list:
    items = []
    for file_name, title, children in nodes:
        counter[0] += 1
        link = epub.Link(file_name, title, f'nav{counter[0]}')
        if children:
            items.append((epub.Section(title, file_name), _toc_items(children, counter)))
        else:
            items.append(link)
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_epub_from_fb2(header: str, body: str, footer: str, output_path: str) -> str:
    """
    Create an EPUB file from FB2-like structure.

    Args:
        header: FB2 header XML string
        body: FB2 body XML string (content of the main <body>)
        footer: FB2 footer with binary blocks (and footnote bodies)
        output_path: Output file path (without extension)

    Returns:
        Path to created EPUB file
    """
    if not body or not body.strip():
        raise ValueError("FB2 body is empty - translation may have failed")

    if config.target_lang.lower() != 'english':
        ascii_ratio = len(re.findall(r'[a-zA-Z]', body)) / len(body)
        if ascii_ratio > 0.7:
            logger.warning(f"High ASCII ratio ({ascii_ratio:.1%}) in FB2 body. "
                           f"May indicate translation failed or content not properly updated.")

    meta = _parse_metadata(header)
    book = epub.EpubBook()
    book.set_identifier(f'urn:uuid:{uuid.uuid4()}')
    book.set_title(meta['title'])
    book.set_language(meta['lang'])
    for i, author in enumerate(meta['authors'], 1):
        book.add_author(author, uid=f'creator{i}')
    if meta['description']:
        book.add_metadata('DC', 'description', meta['description'])
    for genre in meta['genres']:
        book.add_metadata('DC', 'subject', genre)
    if meta['publisher']:
        book.add_metadata('DC', 'publisher', meta['publisher'])
    if meta['series']:
        name, number = meta['series']
        book.add_metadata(None, 'meta', '', {'name': 'calibre:series', 'content': name})
        if number:
            book.add_metadata(None, 'meta', '', {'name': 'calibre:series_index', 'content': str(number)})

    images = _load_images(footer)
    cover_id = meta['cover_id'] if meta['cover_id'] in images else None
    for image_id, info in images.items():
        if image_id == cover_id:
            book.set_cover(info['file_name'], info['data'])
        else:
            book.add_item(epub.EpubItem(uid=info['uid'], file_name=info['file_name'],
                                        media_type=info['content_type'], content=info['data']))

    css = epub.EpubItem(uid='style', file_name='style/book.css', media_type='text/css',
                        content=_CSS.encode('utf-8'))
    book.add_item(css)

    soup, body_root = _xml_soup(body)
    conv = _Converter(soup, images)
    extra_roots = _adopt(soup, [_xml_soup(x)[1] for x in _extra_bodies(footer)])
    toc = conv.build(body_root, extra_roots)

    if not conv.pages:
        raise ValueError("FB2 body has no readable content")

    chapters = []
    for page in conv.pages:
        chapter = epub.EpubHtml(title=page.title, file_name=page.file_name, lang=meta['lang'])
        chapter.content = conv.page_html(page)
        chapter.add_link(href='style/book.css', rel='stylesheet', type='text/css')
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = _toc_items(toc, [0]) or chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = (['cover'] if cover_id else []) + [('nav', 'no')] + chapters

    epub_path = f"{output_path}.epub"
    # epub3_pages: ebooklib would list every element with epub:type + id (our
    # footnotes) in a bogus hidden page-list.
    epub.write_epub(epub_path, book, {'epub3_pages': False})

    if config.debug:
        print(f"EPUB created: {epub_path}")
        print(f"  Files: {len(chapters)}")
        print(f"  Images: {len(images)}")

    try:
        from .epub_repair import validate_epub
        errors = validate_epub(epub_path)
        if errors:
            logger.warning(f"EPUB validation warnings: {len(errors)}")
            for error in errors[:3]:
                logger.warning(f"  {error}")
    except Exception as e:
        if config.debug:
            print(f"EPUB validation warning: {e}")

    return epub_path


def _adopt(soup: BeautifulSoup, roots: List[Tag]) -> List[Tag]:
    """Move already parsed extra bodies into the main soup (single tree)."""
    adopted = []
    for root in roots:
        holder = soup.new_tag('root')
        for child in list(root.children):
            holder.append(child.extract())
        adopted.append(holder)
    return adopted


