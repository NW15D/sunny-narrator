#!/usr/bin/env python3
"""Замер качества готового перевода без LLM: смешанные алфавиты и пол персонажей.

Пример:
    python scripts/translation_audit.py books/The_eternal_moment_ru.epub \\
        --dic books/eternal-moment.pg_ru.dic --lang russian --json logs/audit_before.json
    # после правок — тот же замер и сравнение с прошлым
    python scripts/translation_audit.py books/The_eternal_moment_ru.epub \\
        --dic books/eternal-moment.pg_ru.dic --lang russian --compare logs/audit_before.json

Книга: .epub, .fb2, .txt, .md, .html. Считает теми же функциями, что и
пайплайн:
1. Слова в двух алфавитах («dошло», «Gород») — `script_guard.find_mixed_words`;
   показывает, что из них исправилось бы автоматически, а что осталось бы в логе.
2. Ошибки пола — `gender_check.find_gender_issues`: персонаж из словаря с полом
   he/she — подлежащее, а сказуемое другого рода («Вашти сказал»). Нужна
   spaCy-модель языка перевода (`python -m spacy download ru_core_news_sm`).
3. Персонажи словаря (PERSON) без пола: на них модель пол угадывает.

Местоимения через несколько предложений скрипт не проверяет (как и пайплайн):
смотрите выборку предложений с именами вручную (`--samples`).
"""
import argparse
import collections
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import gender_check, script_guard  # noqa: E402

_PIECE = 50000  # символов на один разбор spaCy


def read_book(path: Path) -> list:
    """Тексты книги по документам (главы EPUB) с разметкой: её пропускают обе проверки."""
    if path.suffix.lower() == '.epub':
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm')))
            docs = [z.read(n).decode('utf-8', errors='replace') for n in names]
        return [re.sub(r'(?s)^.*?<body[^>]*>', '', d) for d in docs]
    return [path.read_text(encoding='utf-8-sig', errors='replace')]


def pieces(text: str) -> list:
    """Куски не длиннее _PIECE, разрезанные по границе абзаца."""
    out = []
    while len(text) > _PIECE:
        cut = text.rfind('\n', 0, _PIECE)
        cut = cut if cut > _PIECE // 2 else _PIECE
        out.append(text[:cut])
        text = text[cut:]
    return out + [text]


def read_dic(path: Path) -> list:
    """Записи словаря (VocabEntry) — тем же загрузчиком, что у пайплайна."""
    from src.vocabulary_manager import VocabularyManager
    return list(VocabularyManager(str(path), dict_file=str(path)).load().values())


def audit(book: Path, dic: Path, lang: str, samples: int) -> dict:
    entries = read_dic(dic)
    targets = [e.target for e in entries]
    mixed, fixable, issues = collections.Counter(), collections.Counter(), []
    for doc in read_book(book):
        for part in pieces(doc):
            _, fixes, unfixed = script_guard.fix_mixed_script(part, lang, targets)
            fixable.update(old for old, _ in fixes)
            mixed.update(old for old, _ in fixes)
            mixed.update(unfixed)
            for issue in gender_check.find_gender_issues(part, entries, lang):
                sentence = re.sub(r'<[^>]+>', '', part[issue.start:issue.end])
                issues.append({'name': issue.name, 'gender': issue.gender, 'words': issue.words,
                               'sentence': ' '.join(sentence.split())[:300]})
    return {
        'book': str(book), 'dic': str(dic), 'lang': lang,
        'gender_checked': gender_check.checks_language(lang),
        'mixed_words': sum(mixed.values()),
        'mixed_fixable': sum(fixable.values()),
        'mixed_top': mixed.most_common(samples),
        'unfixable': sorted(set(mixed) - set(fixable)),
        'gender_issues': len(issues),
        'gender_by_name': collections.Counter(i['name'] for i in issues).most_common(),
        'gender_samples': issues[:samples],
        'persons_without_gender': sorted(e.source for e in entries
                                         if e.category.upper() == 'PERSON' and not e.gender),
    }


def print_report(r: dict, previous: dict = None):
    def delta(key):
        if previous is None or key not in previous:
            return ''
        return f"  (было {previous[key]}, {r[key] - previous[key]:+d})"

    print(f"Книга: {r['book']}\nСловарь: {r['dic']}\nЯзык: {r['lang']}\n")
    print(f"Слова в двух алфавитах: {r['mixed_words']}{delta('mixed_words')}")
    print(f"  исправились бы автоматически: {r['mixed_fixable']}")
    if r['mixed_top']:
        print("  чаще всего: " + ", ".join(f"{w}×{n}" for w, n in r['mixed_top']))
    if r['unfixable']:
        print("  остались бы (в лог): " + ", ".join(r['unfixable']))
    if not r['gender_checked']:
        print("\nПол: не проверяется (язык без рода сказуемого или нет spaCy-модели)")
    else:
        print(f"\nОшибки пола (подлежащее — сказуемое): {r['gender_issues']}{delta('gender_issues')}")
        for name, n in r['gender_by_name']:
            print(f"  {name}: {n}")
        for s in r['gender_samples']:
            print(f"  - {s['name']} ({s['gender']}): «{', '.join(s['words'])}» — {s['sentence']}")
    if r['persons_without_gender']:
        print(f"\nПерсонажи без пола в словаре ({len(r['persons_without_gender'])}): "
              + ", ".join(r['persons_without_gender']))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('book', type=Path)
    parser.add_argument('--dic', type=Path, required=True, help='словарь перевода (.dic)')
    parser.add_argument('--lang', required=True, help='язык перевода (TARGET_LANG)')
    parser.add_argument('--samples', type=int, default=20, help='сколько примеров показать')
    parser.add_argument('--json', type=Path, help='сохранить результат для сравнения')
    parser.add_argument('--compare', type=Path, help='JSON прошлого замера')
    args = parser.parse_args()

    report = audit(args.book, args.dic, args.lang, args.samples)
    previous = json.loads(args.compare.read_text(encoding='utf-8')) if args.compare else None
    print_report(report, previous)
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nСохранено: {args.json}")


if __name__ == '__main__':
    main()
