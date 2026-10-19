"""Описание книги из OPF/метаданных — в обычный текст.

Описание часто лежит как экранированный HTML (``&lt;div&gt;&lt;p&gt;...``):
в титульный лист и метаданные оно должно попасть текстом с абзацами.
"""
import html as _html
import re

_BLOCK_END = re.compile(r'</(?:p|div|li|h[1-6]|blockquote)>|<br\s*/?>', re.IGNORECASE)
_TAG = re.compile(r'<[^>]+>')


def html_to_paragraphs(value: str) -> list[str]:
    """Описание книги → список абзацев обычного текста.

    Понимает и настоящие теги, и экранированные (``&lt;p&gt;``): после
    unescape они становятся тегами, поэтому разбор идёт до и после.
    """
    if not value:
        return []
    # Unescape unconditionally, twice: &lt;p&gt; → <p>, and a doubly escaped
    # description needs another round. The old "stop as soon as a < and a >
    # are present" heuristic left mixed escaped+literal descriptions
    # half-decoded, and &lt;p&gt; fragments reached the title page as text
    # after tag removal (DEF-N4)
    text = _html.unescape(_html.unescape(value))
    text = _BLOCK_END.sub('\n', text)
    text = _TAG.sub('', text)
    text = _html.unescape(text)
    paragraphs = [re.sub(r'[ \t\u00a0]+', ' ', p).strip() for p in text.split('\n')]
    return [p for p in paragraphs if p]


def html_to_text(value: str) -> str:
    """То же, одной строкой: абзацы через пробел."""
    return ' '.join(html_to_paragraphs(value))
