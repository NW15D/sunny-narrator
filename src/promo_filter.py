"""Рекламные вставки сайтов-раздач и HTML в описании книги.

Скачанные книги несут на каждой странице «Downloaded from oceanofpdf.com»,
а описание в OPF/метаданных часто лежит как экранированный HTML
(``&lt;div&gt;&lt;p&gt;...``). Всё это не часть книги: рекламу режем до
перевода, описание превращаем в обычный текст с абзацами.
"""
import html as _html
import re

# Домены раздач. Список короткий намеренно: вырезается только то, что точно
# реклама. Добавить свой — сюда.
PROMO_DOMAINS = ('oceanofpdf.com', 'oceanofpdf.org', 'ebook-hunter.org', 'z-lib.org')

_DOMAIN_RE = '|'.join(re.escape(d) for d in PROMO_DOMAINS)
# Слова и ссылки вокруг домена, которые вместе с ним составляют рекламную строку.
_PROMO_TEXT = re.compile(
    rf'(?:(?:downloaded|provided|brought|available)\s+(?:from|by|at)\s+|'
    rf'(?:https?://)?(?:www\.)?)(?:{_DOMAIN_RE})\S*',
    re.IGNORECASE)
_BARE_PROMO = re.compile(rf'(?:https?://)?(?:www\.)?(?:{_DOMAIN_RE})\S*', re.IGNORECASE)
# Тег целиком: <a ...>…домен…</a>, и абзац, в котором осталась только реклама.
_PROMO_ANCHOR = re.compile(
    rf'<a\b[^>]*>[^<]*(?:{_DOMAIN_RE})[^<]*</a>', re.IGNORECASE)
_PROMO_PARAGRAPH = re.compile(
    rf'<p\b[^>]*>(?:\s|<(?!/?p\b)[^>]+>)*(?:{_DOMAIN_RE})(?:\s|<(?!/?p\b)[^>]+>|[^<\s]{{0,3}})*</p>',
    re.IGNORECASE)

_BLOCK_END = re.compile(r'</(?:p|div|li|h[1-6]|blockquote)>|<br\s*/?>', re.IGNORECASE)
_TAG = re.compile(r'<[^>]+>')


def strip_promo_text(text: str) -> str:
    """Убрать рекламу из простого текста (Markdown, TXT)."""
    if not text:
        return text
    text = _PROMO_TEXT.sub('', text)
    return _BARE_PROMO.sub('', text)


def strip_promo_markup(markup: str) -> str:
    """Убрать рекламу из HTML/XML-строки, не ломая разметку.

    Сначала целые абзацы и ссылки с доменом, потом остаток домена в тексте.
    Теги-атрибуты (href с доменом) уходят вместе со ссылкой.
    """
    if not markup:
        return markup
    markup = _PROMO_PARAGRAPH.sub('', markup)
    markup = _PROMO_ANCHOR.sub('', markup)
    # Остаток — только в тексте между тегами, чтобы не задеть атрибуты.
    return re.sub(r'>([^<]+)<', lambda m: '>' + strip_promo_text(m.group(1)) + '<', markup)


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
    paragraphs = [re.sub(r'[ \t ]+', ' ', p).strip() for p in text.split('\n')]
    return [strip_promo_text(p).strip() for p in paragraphs if p]


def html_to_text(value: str) -> str:
    """То же, одной строкой: абзацы через пробел."""
    return ' '.join(p for p in html_to_paragraphs(value) if p)
