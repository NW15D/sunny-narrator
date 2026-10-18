"""
Every relative link of the public Markdown files (README*, AGENTS,
CONTRIBUTING, docs/, .github templates) points to a file that exists, and
every #anchor to a heading of its target - pages were renamed and merged and
the links kept pointing at the old ones. GitHub's anchor rules: lowercase,
punctuation dropped (Unicode letters kept), spaces to hyphens, -1, -2 for
repeated headings; links inside code blocks are not links.
"""
import glob
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
PRIVATE = {'CLAUDE.md'}  # not published


def _files():
    paths = (glob.glob(os.path.join(ROOT, '*.md')) + glob.glob(os.path.join(ROOT, 'docs', '*.md'))
             + glob.glob(os.path.join(ROOT, '.github', '**', '*.md'), recursive=True))
    return sorted(os.path.normpath(p) for p in paths if os.path.basename(p) not in PRIVATE)


def _text(path):
    with open(path, encoding='utf-8') as f:
        return re.sub(r'```.*?```', '', f.read(), flags=re.S)


def _anchors(path):
    seen, out = {}, set()
    for heading in re.findall(r'^#{1,6}\s+(.*)$', _text(path), re.M):
        slug = re.sub(r'[^\w\- ]', '', heading.replace('`', '').strip().lower()).replace(' ', '-')
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f'{slug}-{n}')
    return out


@pytest.mark.parametrize('path', _files(), ids=lambda p: os.path.relpath(p, ROOT))
def test_relative_links_resolve(path):
    broken = []
    for target in re.findall(r'\]\(([^)\s]+)\)', _text(path)):
        if target.startswith(('http://', 'https://', 'mailto:')) or target.startswith('sn-'):
            continue  # sn-imgref-N: the placeholder format, not a link
        file_part, _, anchor = target.partition('#')
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), file_part)) if file_part else path
        if file_part and not os.path.exists(resolved):
            broken.append(f"{target}: no such file")
        elif anchor and resolved.endswith('.md') and anchor.lower() not in _anchors(resolved):
            broken.append(f"{target}: no such heading")
    assert not broken, broken
