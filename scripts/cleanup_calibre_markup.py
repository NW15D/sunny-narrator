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


def cleanup_calibre_markup(text: str) -> str:
    """Удалить Calibre-маркеры из текста."""
    
    if not text or not text.strip():
        return text
    
    # Remove Calibre comment markers like: <!-- 1 -->
    text = re.sub(r'<!--\s*\d+\s*-->', '', text)
    
    # Remove Calibre section markers in HTML format (:::{...}::: inside <div> or <p>)
    text = re.sub(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', '', text, flags=re.DOTALL)
    
    # Remove standalone :::
    text = re.sub(r'<[^>]*>:::</[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r':::', '', text)
    
    # Remove HTML paragraph包围的 Calibre markers
    text = re.sub(r'<p>\s*\{#.*?\}\s*</p>', '', text, flags=re.DOTALL)
    
    # Remove inline Calibre markers: {#calibre_link-* .calibre*} and {#annotation .calibre*}
    # Use broad pattern to catch all {#...} and {.class} markers
    text = re.sub(r'\{#[^}]+\}', '', text)  # {#calibre_link-0 .calibre} and similar
    text = re.sub(r'\{\.\w+\}', '', text)  # {.calibre1} and similar
    
    # Remove Calibre IDs: id="calibre_link-*"
    text = re.sub(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', '', text, flags=re.IGNORECASE)
    
    # Remove Calibre class attributes from HTML tags
    text = re.sub(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', '', text, flags=re.IGNORECASE)
    
    # Remove horizontal rules that are Calibre section markers
    text = re.sub(r'\n*---\s*\n*', '\n\n', text)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
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
