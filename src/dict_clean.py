"""
Cleaning of a .dic before its review (`app.py dict clean`). The source file
is not changed: the result is `<name>.clean.dic` (or `output`), every change
is listed in `<result>.report.txt`.

1. Fields: the category upper-cased (a lowercase entry without one becomes
   TERM); the gender spellings (он/она, male/female, м/ж, ...) become
   he/she/it/they (gender_check.GENDER_MAP, the loader's list); an unknown
   value stays and is reported (the loader ignores it).
2. Duplicates of one entry ("Jain tech" / "jain tech", lexicon.word_key as in
   the loader; "Jain-tech" is another entry) merge into one: the one with a
   category and a capital wins, else the first; empty gender and notes are
   filled from the others. Different translations are reported.
3. Ordinary words: a one-word lowercase entry the spaCy model has a vector for
   (ner.known_words; NERMODEL or `model`) is dropped, except `keep`. A model
   without vectors (*_sm) drops nothing.
4. Cut variants: with the same translation an entry 1-2 letters longer than
   another and not an ordinary word ("Jains" next to "Jain") is dropped.

Lines are written in the CSV format of build_dictionary and dict_convert, so
the loader reads the result without losses.
"""
import collections
import csv
import io
import os
from pathlib import Path

from src import lexicon
from src import ner
from src.gender_check import GENDER_MAP  # the loader normalizes the same way

REPORT_EXT = '.report.txt'  # <result>.report.txt next to the result
CATEGORY_ORDER = ['PERSON', 'GPE', 'LOC', 'FAC', 'ORG', 'PRODUCT', 'EVENT', 'TERM']


def parse_dic(path: Path, report, keep_empty_target: bool = False):
    """Записи файла: dict(source, target, category, gender, notes, line) —
    line: индекс строки в text.splitlines()."""
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
        if not source or (not fields[0] and not keep_empty_target):
            report['skipped'].append(f"{num}: {line}")
            continue
        # unquoted notes with commas (older files): keep all of them
        notes = ', '.join(f for f in fields[3:] if f)
        rows.append(dict(source=source, target=fields[0], category=fields[1],
                         gender=fields[2], notes=notes, line=num - 1))
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


def clean_file(dic: Path, output: Path = None, report_path: Path = None,
               model: str = None, keep: str = '') -> dict:
    """Clean `dic` into `output` (default <name>.clean.dic) with a report;
    returns {'output', 'report', 'before', 'after', 'counts'}."""
    output = output or dic.with_name(f"{dic.stem}.clean.dic")
    report_path = report_path or output.with_name(f"{output.stem}{REPORT_EXT}")
    if output.resolve() == dic.resolve():
        raise ValueError('the result must not overwrite the source file')
    if model:
        ner.config.nermodel = model
    keep = {w.strip().casefold() for w in keep.split(',') if w.strip()}

    report = collections.defaultdict(list)
    rows = parse_dic(dic, report)
    total = len(rows)
    for row in rows:
        normalize_fields(row, report)
    rows = merge_duplicates(rows, report)
    rows, ordinary = drop_ordinary_words(rows, keep, report)
    rows = drop_cut_variants(rows, ordinary, report)

    write_atomic(output, render(rows, dic.name))
    write_atomic(report_path, ''.join(f"## {k} ({len(v)})\n" + '\n'.join(v) + '\n\n'
                                      for k, v in report.items()))
    return {'output': output, 'report': report_path, 'before': total, 'after': len(rows),
            'counts': {k: len(v) for k, v in report.items()}}
