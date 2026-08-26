"""Валидация формата .dic-файла.

Порт грамматики из validate_dictionary() в родительском проекте
(../src/vocabulary_manager.py) — та же логика "source = target, category,
gender, notes" с #-комментариями, но работает над текстом в памяти
(bytes/str из UploadFile), а не над путём к файлу на диске, и не тянет
зависимость на src.config.Config (front-dic должен уметь разворачиваться
отдельно от sunny-narrator). При изменении грамматики в исходном проекте
эту копию нужно поправить вручную — общего пакета между репозиториями
пока нет.
"""

import csv
import re
from typing import List, Tuple

_CSV_PATTERN = re.compile(r"^[^=]+=\s*\S+")


def validate_dic_content(text: str) -> Tuple[List[str], int]:
    """Возвращает (список ошибок, число валидных записей).

    Список ошибок пуст, если файл валиден.
    """
    errors: List[str] = []
    lines = text.splitlines()

    entry_lines = []
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entry_lines.append((line_num, stripped))

    if not entry_lines:
        return ["Файл пуст (нет записей)"], 0

    sources_seen: List[str] = []
    for line_num, line in entry_lines:
        if not _CSV_PATTERN.match(line):
            errors.append(f"Строка {line_num}: не соответствует формату 'source = target': {line[:80]}")
            continue

        source = line.split("=", 1)[0].strip()
        rest = line.split("=", 1)[1].strip()
        try:
            row = next(csv.reader([rest]))
            target = row[0].strip() if row else ""
        except (StopIteration, csv.Error):
            target = ""

        if not source or not target:
            errors.append(f"Строка {line_num}: пустой source или target: {line[:80]}")
            continue

        sources_seen.append(source.lower())

    duplicates = {s for s in sources_seen if sources_seen.count(s) > 1}
    if duplicates:
        errors.append(f"Повторяющиеся source-термины: {', '.join(sorted(duplicates))}")

    return errors, len(entry_lines)
