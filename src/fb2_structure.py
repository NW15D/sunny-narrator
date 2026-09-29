"""Structure-aware helpers for FB2 body fragments.

The classic pipeline translates a book chunk by chunk and glues the results
back together. If tag balance is only "fixed" globally at the end (append the
missing </p> / </section> before </body>), one dropped closer in chunk 12 turns
into a pile of closers at the end of the book and wrecks everything between.
Everything here works locally instead:

* split_body_units / chunk_unit_content cut the source body along its real
  structure, so every chunk is balanced by construction;
* repair_fragment fixes a translated chunk at the exact spot where the LLM
  broke it, using the FB2 content model (a <p> cannot contain a block, a
  section holds either sections or blocks, ...);
* close_dangling_sections only ever appends closers for a truncated tail.
"""

import html
import html.entities
import re
from typing import Dict, List, NamedTuple, Optional, Tuple

_TAG_RE = re.compile(r'<(/?)([A-Za-z][\w:.-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*?)(/?)>')
_SECTION_TAG_RE = re.compile(
    r'<(/?)section\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*?)(/?)>', re.IGNORECASE)

# Void elements for *splitting* the source (br/hr never occur in valid FB2 but
# must not unbalance the depth counter if a converted book contains them).
_SPLIT_VOID = {'empty-line', 'image', 'br', 'hr'}

# FB2 element classes used by the content-model rules below.
_PARA = {'p', 'v', 'subtitle', 'text-author', 'date', 'th', 'td'}
_INLINE = {'strong', 'emphasis', 'style', 'a', 'strikethrough', 'sub', 'sup', 'code'}
_BLOCK_CONTAINERS = {'poem', 'stanza', 'cite', 'epigraph', 'title',
                     'annotation', 'history', 'table', 'tr'}
_BLOCKISH = _PARA | _BLOCK_CONTAINERS
_VOID = {'empty-line', 'image'}
_KNOWN = _BLOCKISH | _INLINE | _VOID | {'section'}
# Elements that count as the "blocks" branch of a section (as opposed to its
# title/epigraph/image/annotation header, which may precede nested sections).
_CONTENT_BLOCKS = {'p', 'poem', 'subtitle', 'cite', 'empty-line', 'table'}
# Parents whose direct text has to live inside a <p> (or <v> in a stanza).
_WRAP_CTX = {'section', 'poem', 'cite', 'epigraph', 'annotation', 'history',
             'title', 'stanza'}
_ALIASES = {'b': 'strong', 'bold': 'strong', 'i': 'emphasis', 'em': 'emphasis',
            'italic': 'emphasis', 'u': 'emphasis', 's': 'strikethrough',
            'strike': 'strikethrough', 'del': 'strikethrough'}
_SPLITTABLE = {'poem', 'cite', 'epigraph', 'annotation', 'history'}


class Unit(NamedTuple):
    """Direct content of one section, cut at nested-section boundaries.

    open_tag is the original ``<section ...>`` tag when the unit starts a new
    section, None for content that continues an already open section (or sits
    at body level, depth 0). depth is the nesting level of the owning section.
    """
    open_tag: Optional[str]
    depth: int
    content: str


# ---------------------------------------------------------------------------
# Splitting the source body
# ---------------------------------------------------------------------------

def _strip_body_wrapper(body: str) -> str:
    body = re.sub(r'^\s*<body\b[^>]*>', '', body, count=1)
    return re.sub(r'</body>\s*$', '', body, count=1)


def _open_tag(m: 're.Match') -> str:
    return re.sub(r'\s*/>$', '>', m.group(0))


def split_body_units(body: str) -> List[Unit]:
    """Flatten the section tree into document-ordered units.

    Nothing is dropped: body-level title/epigraph before the first section,
    text between nested sections and the tail of a parent after its last child
    all become units of their own. A body without any <section> becomes one
    section so the result is still a valid FB2 body.
    """
    body = _strip_body_wrapper(body)
    if not _SECTION_TAG_RE.search(body):
        return [Unit('<section>', 1, body)] if body.strip() else []

    units: List[Unit] = []
    depth = 0
    start = 0
    pending_open: Optional[str] = None

    def flush(end: int) -> None:
        nonlocal pending_open
        content = body[start:end]
        if pending_open is not None or content.strip():
            units.append(Unit(pending_open, depth, content))
        pending_open = None

    for m in _SECTION_TAG_RE.finditer(body):
        closing, _attrs, selfclose = m.groups()
        flush(m.start())
        if closing:
            if depth > 0:
                depth -= 1
        elif selfclose:
            units.append(Unit(_open_tag(m), depth + 1, ''))
        else:
            depth += 1
            pending_open = _open_tag(m)
        start = m.end()
    flush(len(body))
    return units


def split_blocks(text: str) -> List[str]:
    """Split a fragment into its top-level elements (each one balanced)."""
    blocks: List[str] = []
    depth = 0
    start = 0
    for m in _TAG_RE.finditer(text):
        closing, name, _attrs, selfclose = m.groups()
        name = name.lower()
        if selfclose or name in _SPLIT_VOID:
            if depth == 0:
                blocks.append(text[start:m.end()])
                start = m.end()
        elif closing:
            if depth == 0:
                continue
            depth -= 1
            if depth == 0:
                blocks.append(text[start:m.end()])
                start = m.end()
        else:
            depth += 1
    if start < len(text):
        blocks.append(text[start:])
    return blocks


def _glue_blocks(blocks: List[str]) -> List[str]:
    """Keep a container's title/epigraph with its first real block and a
    trailing text-author/date with the last one, so no split part is a poem
    without stanzas or a cite without paragraphs."""
    glued: List[str] = []
    pending = ''
    for b in blocks:
        head = b.lstrip()
        if head.startswith(('<title', '<epigraph')):
            pending += b
        elif glued and head.startswith(('<text-author', '<date')):
            glued[-1] += b
        else:
            glued.append(pending + b)
            pending = ''
    if pending:
        glued.append(pending)
    return glued


def _fit_block(block: str, max_len: int) -> List[str]:
    """Split an oversized container into several balanced containers."""
    if len(block) <= max_len:
        return [block]
    m = _TAG_RE.search(block)
    if not m or m.group(1) or m.group(4) or block[:m.start()].strip():
        return [block]
    name = m.group(2).lower()
    close = re.search(rf'</{re.escape(name)}\s*>\s*$', block)
    if name not in _SPLITTABLE or not close:
        return [block]
    open_tag = m.group(0)
    inner = block[m.end():close.start()]
    parts = _pack_blocks(_glue_blocks(split_blocks(inner)), max(max_len - len(open_tag) - len(name) - 3, 1))
    if len(parts) <= 1:
        return [block]
    return [f'{open_tag}{p}</{name}>' for p in parts]


def _pack_blocks(blocks: List[str], max_len: int) -> List[str]:
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for block in blocks:
        for piece in _fit_block(block, max_len):
            if cur and cur_len + len(piece) > max_len:
                chunks.append(''.join(cur))
                cur, cur_len = [], 0
            cur.append(piece)
            cur_len += len(piece)
    if cur:
        chunks.append(''.join(cur))
    return chunks


def chunk_unit_content(content: str, max_len: int) -> List[str]:
    """Pack a unit's blocks into chunks of about max_len chars.

    Boundaries only fall between top-level blocks, so a poem, a cite or a
    table is never cut in half. A single block bigger than max_len is kept
    whole (translate_chunk has its own length-based rechunking for that).
    """
    return [c.strip() for c in _pack_blocks(split_blocks(content), max_len) if c.strip()]


def prepare_body_structure(body: str, max_len_chunk: int) -> Tuple[List[List[str]], List[Dict]]:
    """Return (sections, meta): chunks per unit and each unit's open_tag/depth."""
    units = split_body_units(body)
    sections = [chunk_unit_content(u.content, max_len_chunk) for u in units]
    meta = [{'open_tag': u.open_tag, 'depth': u.depth} for u in units]
    return sections, meta


def section_transition(unit_meta: Dict, cur_depth: int) -> Tuple[str, int]:
    """Text to emit before a unit's content, and the resulting open depth."""
    depth = unit_meta['depth']
    open_tag = unit_meta.get('open_tag')
    if open_tag:
        return '</section>\n' * max(cur_depth - (depth - 1), 0) + open_tag + '\n', depth
    return '</section>\n' * max(cur_depth - depth, 0), depth


def close_dangling_sections(content: str) -> str:
    """Drop stray </section> and close sections left open by a truncated tail."""
    depth = 0
    out: List[str] = []
    pos = 0
    for m in _SECTION_TAG_RE.finditer(content):
        closing, _attrs, selfclose = m.groups()
        if selfclose:
            continue
        if not closing:
            depth += 1
        elif depth == 0:
            out.append(content[pos:m.start()])
            pos = m.end()
        else:
            depth -= 1
    out.append(content[pos:])
    result = ''.join(out)
    if depth:
        result = result.rstrip('\n') + '\n' + '</section>\n' * depth
    return result


# ---------------------------------------------------------------------------
# Repairing a fragment
# ---------------------------------------------------------------------------

_XML_ENTITIES = {'amp', 'lt', 'gt', 'quot', 'apos'}
_NAMED_ENTITY_RE = re.compile(r'&([A-Za-z][A-Za-z0-9]*);')
_BARE_AMP_RE = re.compile(r'&(?!(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)')
_BARE_LT_RE = re.compile(r'<(?!!--|!\[CDATA\[|\?)')


def _fix_text(seg: str) -> str:
    """Make a text run XML-safe: HTML-only entities, bare & and bare <."""
    def entity(m: 're.Match') -> str:
        name = m.group(1)
        if name in _XML_ENTITIES:
            return m.group(0)
        cp = html.entities.name2codepoint.get(name)
        return chr(cp) if cp else f'&amp;{name};'

    seg = _NAMED_ENTITY_RE.sub(entity, seg)
    seg = _BARE_AMP_RE.sub('&amp;', seg)
    return _BARE_LT_RE.sub('&lt;', seg)


def visible_text(xml: str) -> str:
    """Text content with tags, entities and whitespace normalised away."""
    xml = re.sub(r'<!--.*?-->|<\?.*?\?>|<!DOCTYPE[^>]*>', '', xml.replace('\ufeff', ''), flags=re.DOTALL)
    return re.sub(r'\s+', '', html.unescape(_TAG_RE.sub('', xml)))


def strip_code_fences(text: str) -> str:
    return re.sub(r'^\s*```[A-Za-z0-9]*[ \t]*\n|\n[ \t]*```\s*$', '', text)


def repair_fragment(text: str, *, keep_sections: bool = False,
                    strip_unknown: bool = True, wrap_text: bool = True) -> str:
    """Rebalance a fragment locally, without ever dropping text.

    Well-formed FB2 comes back unchanged. Otherwise: orphan closers are
    dropped, tags that are still open when a tag which cannot live inside them
    starts (or when their parent closes) are closed right there, bare text
    where FB2 wants a paragraph is wrapped in <p>/<v>, and stray & / < are
    escaped. With keep_sections a <section> that already holds blocks and then
    meets another <section> is closed at that point, which is how a lost
    </section> is found where it belongs instead of at the end of the book.
    Without keep_sections all section tags are dropped (chunks are pieces of
    one section; the section frame is emitted by the caller).
    """
    out: List[str] = []
    stack: List[str] = []
    flags: List[bool] = []  # parallel to stack: section already has block content

    def push(name: str) -> None:
        stack.append(name)
        flags.append(False)

    def close_top() -> None:
        out.append(f'</{stack.pop()}>')
        flags.pop()

    def close_through(idx: int) -> None:
        while len(stack) > idx:
            close_top()

    def close_para() -> None:
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] in _PARA:
                close_through(i)
                return

    def needs_wrapper() -> bool:
        return wrap_text and (not stack or stack[-1] in _WRAP_CTX)

    def mark_block(name: str) -> None:
        if name in _CONTENT_BLOCKS and stack and stack[-1] == 'section':
            flags[-1] = True

    def open_implicit() -> None:
        name = 'v' if stack and stack[-1] == 'stanza' else 'p'
        mark_block(name)
        push(name)
        out.append(f'<{name}>')

    def emit_text(seg: str) -> None:
        if not seg:
            return
        seg = _fix_text(seg)
        if not seg.strip() or not needs_wrapper():
            out.append(seg)
            return
        pieces = [p for p in re.split(r'\n\s*\n', seg) if p.strip()]
        for i, piece in enumerate(pieces):
            open_implicit()
            out.append(piece.strip())
            if i < len(pieces) - 1:
                close_top()
                out.append('\n')

    pos = 0
    for m in _TAG_RE.finditer(text):
        emit_text(text[pos:m.start()])
        pos = m.end()
        closing, raw_name, attrs, selfclose = m.groups()
        name = raw_name.lower()
        if strip_unknown:
            name = _ALIASES.get(name, name)
            if name not in _KNOWN:
                continue

        if name == 'section' and not keep_sections:
            continue

        if closing:
            if name in _VOID or name not in stack:
                continue
            idx = len(stack) - 1 - stack[::-1].index(name)
            close_through(idx + 1)
            close_top()
            continue

        if name in _VOID:
            if name == 'empty-line':
                close_para()
                mark_block(name)
            out.append(f'<{name}{attrs.rstrip()}/>')
            continue
        if selfclose:
            continue

        if name == 'section':
            while stack and stack[-1] != 'section':
                close_top()
            while stack and flags[-1]:
                close_top()
                while stack and stack[-1] != 'section':
                    close_top()
        elif name in _BLOCKISH:
            close_para()
            if name in stack:
                close_through(len(stack) - 1 - stack[::-1].index(name))
            mark_block(name)
        elif name in _INLINE and needs_wrapper():
            open_implicit()

        push(name)
        out.append(m.group(0) if name == raw_name else f'<{name}{attrs}>')

    emit_text(text[pos:])
    close_through(0)
    return ''.join(out)


def sanitize_translated_chunk(translated: str) -> str:
    """Clean one translated chunk before it is glued into the book."""
    text = strip_code_fences(translated.strip())
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return repair_fragment(text).strip()
