#!/usr/bin/env python3
"""
Утилита для удаления артефактов Calibre из FB2 и HTML файлов.

Очищает:
- :::{#calibre_link-* .calibre*}::: маркеры
- {#calibre_link-* .calibre*} inline маркеры
- .calibre* классы
- id="calibre_link-*"
"""

import re
import sys
from pathlib import Path

# Precompiled Calibre-specific cleanup patterns (narrowed to avoid removing valid Pandoc attributes)
_RE_CALIBRE_COMMENT = re.compile(r'<!--\s*\d+\s*-->')
_RE_CALIBRE_SECTION_FULL = re.compile(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_CLASS = re.compile(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_SECTION_BARE = re.compile(r'<[^>]*>:::</[^>]*>', re.DOTALL)
_RE_CALIBRE_TRIPLE_COLON = re.compile(r':::')
_RE_CALIBRE_PARA = re.compile(r'<p>\s*\{#calibre[^}]*\}\s*</p>', re.DOTALL)
_RE_CALIBRE_ANCHOR = re.compile(r'\{#calibre[^}]*\}')  # Only calibre-specific anchors
_RE_CALIBRE_CLASS = re.compile(r'\{\.calibre\d*\}')  # Only calibre-specific classes
_RE_CALIBRE_ID_ATTR = re.compile(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', re.IGNORECASE)
_RE_CALIBRE_CLASS_ATTR = re.compile(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', re.IGNORECASE)
_RE_HR_MARKERS = re.compile(r'\n*---\s*\n*')
_RE_MULTI_BLANK = re.compile(r'\n{3,}')


def cleanup_calibre_markup(text: str) -> str:
    """Удалить Calibre-маркеры из текста."""
    
    if not text or not text.strip():
        return text
    
    # Remove Calibre comment markers like: <!-- 1 -->
    text = _RE_CALIBRE_COMMENT.sub('', text)
    
    # Remove Calibre section markers in HTML format (:::{...}::: inside <div> or <p>)
    text = _RE_CALIBRE_SECTION_FULL.sub('', text)
    text = _RE_CALIBRE_SECTION_CLASS.sub('', text)
    
    # Remove standalone :::
    text = _RE_CALIBRE_SECTION_BARE.sub('', text)
    text = _RE_CALIBRE_TRIPLE_COLON.sub('', text)
    
    # Remove HTML paragraphs containing only Calibre markers
    text = _RE_CALIBRE_PARA.sub('', text)
    
    # Remove inline Calibre markers (narrowed to Calibre-specific only)
    text = _RE_CALIBRE_ANCHOR.sub('', text)  # {#calibre_link-0 .calibre} and similar
    text = _RE_CALIBRE_CLASS.sub('', text)  # {.calibre1} and similar
    
    # Remove Calibre IDs: id="calibre_link-*"
    text = _RE_CALIBRE_ID_ATTR.sub('', text)
    
    # Remove Calibre class attributes from HTML tags
    text = _RE_CALIBRE_CLASS_ATTR.sub('', text)
    
    # Remove horizontal rules that are Calibre section markers
    text = _RE_HR_MARKERS.sub('\n\n', text)
    
    # Clean up multiple blank lines
    text = _RE_MULTI_BLANK.sub('\n\n', text)
    
    # Remove leading/trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


def process_file(filepath: Path) -> str:
    """Обработать один файл и вернуть очищенный контент."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    cleaned = cleanup_calibre_markup(content)
    return cleaned


def main():
    if len(sys.argv) < 2:
        print("Использование: python cleanup_calibre_markup.py <file> [--inplace]")
        print("file: FB2, HTML, or any text file with Calibre markers")
        sys.exit(1)

    filepath = Path(sys.argv[1])

    if not filepath.exists():
        print(f"Файл не найден: {filepath}")
        sys.exit(1)

    cleaned_content = process_file(filepath)

    if '--inplace' in sys.argv:
        # Перезаписать исходный файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
        print(f"Файл обновлён: {filepath}")
    else:
        # Вывод в stdout
        print(cleaned_content)


if __name__ == '__main__':
    main()
