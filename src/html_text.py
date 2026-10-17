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
    text = value
    for _ in range(2):  # &lt;p&gt; → <p>; двойное экранирование встречается
        if '<' in text and '>' in text:
            break
        text = _html.unescape(text)
    text = _BLOCK_END.sub('\n', text)
    text = _TAG.sub('', text)
    text = _html.unescape(text)
    paragraphs = [re.sub(r'[ \t\u00a0]+', ' ', p).strip() for p in text.split('\n')]
    return [p for p in paragraphs if p]


def html_to_text(value: str) -> str:
    """То же, одной строкой: абзацы через пробел."""
    return ' '.join(html_to_paragraphs(value))
