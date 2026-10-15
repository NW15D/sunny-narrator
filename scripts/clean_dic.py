#!/usr/bin/env python3
"""Чистка словаря .dic перед ручной проверкой.

Пример:
    python scripts/clean_dic.py books/MyBook.dic
    python scripts/clean_dic.py books/MyBook.dic -o books/MyBook_clean.dic --keep runcible,autogun

Исходный файл не меняется. Результат — `<имя>.clean.dic` рядом с исходником
(или `-o`), отчёт о каждом изменении — `<результат>.report.txt` (или `--report`).

Шаги:
1. Поля: категория — в верхний регистр (у записи в нижнем регистре без
   категории — TERM); пол — синонимы (он/она/оно/они, male/female, м/ж, …)
   приводятся к he/she/it/they (тот же список, что у загрузчика,
   `gender_check.GENDER_MAP`). Незнакомое значение пола остаётся как есть и
   попадает в отчёт: загрузчик его не принимает (пишет в лог), поправьте вручную.
2. Дубли одной записи (`Jain tech` / `jain tech`, по `lexicon.word_key`, как
   в загрузчике; `Jain-tech` — другая запись) сливаются в одну: остаётся
   запись с категорией и с заглавной буквой, при равенстве — первая в файле;
   пустые пол и заметки дополняются из остальных. Разные переводы — в отчёт.
3. Обычные слова: однословная запись в нижнем регистре, у которой есть вектор
   в spaCy-модели (`ner.known_words`; модель — NERMODEL / по SOURCE_LANG или
   `--model`), удаляется. `--keep` — слова, которые оставить. С моделью без
   векторов (*_sm) шаг ничего не удаляет.
4. Обрезанные варианты: при том же переводе запись, которая длиннее другой на
   1–2 буквы и не является обычным словом (`Jains` при `Jain`), удаляется.

Строки пишутся тем же CSV-форматом, что у `build_dictionary` и
`convert_dic.py`: поле с запятой или кавычкой берётся в кавычки, кавычки
внутри удваиваются, поэтому файл читается загрузчиком без потерь.
"""
import argparse
import collections
import csv
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import lexicon  # noqa: E402
from src import ner  # noqa: E402
from src.gender_check import GENDER_MAP  # noqa: E402  (the loader normalizes the same way)

CATEGORY_ORDER = ['PERSON', 'GPE', 'LOC', 'FAC', 'ORG', 'PRODUCT', 'EVENT', 'TERM']


def parse_dic(path: Path, report):
    """Записи файла: dict(source, target, category, gender, notes)."""
    rows = []
    for num, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            report['skipped'].append(f"{num}: {line}")
            continue
        source, rest = (p.strip() for p in line.split('=', 1))
        try:
            fields = [f.strip() for f in next(csv.reader([rest]), [])]
        except csv.Error:
            fields = []
        fields += [''] * (4 - len(fields))
        if not source or not fields[0]:
            report['skipped'].append(f"{num}: {line}")
            continue
        # unquoted notes with commas (older files): keep all of them
        notes = ', '.join(f for f in fields[3:] if f)
        rows.append(dict(source=source, target=fields[0], category=fields[1],
                         gender=fields[2], notes=notes))
    return rows


def normalize_fields(row, report):
    row['category'] = row['category'].upper()
    if not row['category'] and row['source'] == row['source'].lower():
        row['category'] = 'TERM'
    gender = row['gender']
    if gender:
        canonical = GENDER_MAP.get(gender.casefold())
        if canonical:
            row['gender'] = canonical
        else:
            report['unknown gender (kept)'].append(f"{row['source']}: {gender}")


def merge_duplicates(rows, report):
    groups = collections.OrderedDict()
    for row in rows:
        groups.setdefault(lexicon.word_key(row['source']), []).append(row)
    merged = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        # stable: the first line of the file wins among equals
        best = dict(min(group, key=lambda r: (not r['category'], not r['source'][:1].isupper())))
        for row in group:
            best['gender'] = best['gender'] or row['gender']
            best['notes'] = best['notes'] or row['notes']
        targets = {r['target'] for r in group}
        label = 'merged, different targets' if len(targets) > 1 else 'merged'
        report[label].append(' | '.join(f"{r['source']} = {r['target']}" for r in group)
                             + f"  ->  {best['source']} = {best['target']}")
        merged.append(best)
    return merged


def drop_ordinary_words(rows, keep, report):
    candidates = [r['source'] for r in rows
                  if r['source'] == r['source'].lower() and r['source'].casefold() not in keep]
    ordinary = ner.known_words(candidates)
    kept = []
    for row in rows:
        if row['source'] in ordinary:
            report['ordinary word'].append(f"{row['source']} = {row['target']}")
        else:
            kept.append(row)
    return kept, ordinary


def drop_cut_variants(rows, ordinary, report):
    by_target = collections.defaultdict(list)
    for row in rows:
        by_target[row['target'].casefold()].append(row)
    drop = set()
    for group in by_target.values():
        for short in group:
            for long in group:
                s, lng = short['source'].casefold(), long['source'].casefold()
                if (long is not short and 0 < len(lng) - len(s) <= 2 and lng.startswith(s)
                        and long['source'] not in ordinary):
                    drop.add(id(long))
                    report['cut variant'].append(f"{long['source']} (= {short['source']}) = {long['target']}")
    return [r for r in rows if id(r) not in drop]


def format_line(row):
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerow(
        [row['target'], row['category'], row['gender'], row['notes']])
    return f"{row['source']} = {buf.getvalue().rstrip()}"


def write_atomic(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + '.building')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def render(rows, src_name: str) -> str:
    lines = [f"# Vocabulary {src_name} (cleaned)",
             "# Format: source = target, category, gender, notes", ""]
    categories = CATEGORY_ORDER + sorted({r['category'] for r in rows} - set(CATEGORY_ORDER))
    for category in categories:
        group = [r for r in rows if r['category'] == category]
        if group:
            lines.append(f"# {category or 'no category'} ({len(group)} terms)")
            lines += [format_line(r) for r in group]
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dic', type=Path, help='исходный .dic')
    ap.add_argument('-o', '--output', type=Path, help='результат (по умолчанию <имя>.clean.dic)')
    ap.add_argument('--report', type=Path, help='отчёт (по умолчанию <результат>.report.txt)')
    ap.add_argument('--model', default=ner.config.nermodel,
                    help=f'spaCy-модель для обычных слов (по умолчанию {ner.config.nermodel})')
    ap.add_argument('--keep', default='', help='слова через запятую, которые не удалять как обычные')
    args = ap.parse_args()

    output = args.output or args.dic.with_name(f"{args.dic.stem}.clean.dic")
    report_path = args.report or output.with_name(f"{output.stem}.report.txt")
    if output.resolve() == args.dic.resolve():
        ap.error('результат не должен совпадать с исходным файлом')
    ner.config.nermodel = args.model
    keep = {w.strip().casefold() for w in args.keep.split(',') if w.strip()}

    report = collections.defaultdict(list)
    rows = parse_dic(args.dic, report)
    total = len(rows)
    for row in rows:
        normalize_fields(row, report)
    rows = merge_duplicates(rows, report)
    rows, ordinary = drop_ordinary_words(rows, keep, report)
    rows = drop_cut_variants(rows, ordinary, report)

    write_atomic(output, render(rows, args.dic.name))
    write_atomic(report_path, ''.join(f"## {k} ({len(v)})\n" + '\n'.join(v) + '\n\n'
                                      for k, v in report.items()))
    print(f"{total} -> {len(rows)} entries: {output}")
    for k, v in report.items():
        print(f"  {k}: {len(v)}")
    print(f"report: {report_path}")


if __name__ == '__main__':
    main()
