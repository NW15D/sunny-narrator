#!/usr/bin/env python3
"""Прогон отрывков-ловушек через настоящий пайплайн: проверка промптов на ваших моделях.

Пример:
    python scripts/prompt_eval.py books/eternal-moment.pg.epub \\
        --dic books/eternal-moment.pg_ru.dic --count 8 --out logs/eval/before.json
    # после правки промптов или моделей — те же отрывки и сравнение
    python scripts/prompt_eval.py books/eternal-moment.pg.epub \\
        --dic books/eternal-moment.pg_ru.dic --count 8 --out logs/eval/after.json \\
        --compare logs/eval/before.json

Настройки (модели, ключи, TARGET_LANG, FAST_TRANS, GENDER_CHECK, температуры)
берутся из .env, как у обычного запуска. Скрипт:
1. Режет исходник на отрывки по `--size` символов (по границе абзацев) и берёт
   `--count` отрывков, где больше всего упоминаний персонажей с полом из словаря
   (или `--names`) и местоимений he/she: там модель чаще всего путает пол.
   Выбор детерминированный: при тех же файлах — те же отрывки.
2. Переводит каждый через `translate_chunk` — все стадии, включая GENDER.
3. Считает по готовым переводам то же, что `translation_audit.py`: слова в двух
   алфавитах и ошибки пола, плюс счётчики пайплайна (сколько исправлено по ходу).
4. Сохраняет JSON (для `--compare`) и рядом `.md` с исходником и переводом
   каждого отрывка — местоимения через несколько предложений проверяйте глазами.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.translation_audit import read_book, read_dic  # noqa: E402
from src import gender_check, lexicon, script_guard  # noqa: E402
from src import utils  # noqa: E402  (нужны ключи API из .env)

_PRONOUNS = re.compile(r"\b(?:he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE)


def plain_paragraphs(doc: str) -> list:
    doc = re.sub(r'(?is)<(script|style|head)[^>]*>.*?</\1>', ' ', doc)
    doc = re.sub(r'(?i)</(p|div|h\d|li|blockquote|v|title|subtitle)>', '\n\n', doc)
    text = re.sub(r'<[^>]+>', ' ', doc)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
            .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def passages(book: Path, size: int) -> list:
    out = []
    for doc in read_book(book):
        current = ''
        for para in plain_paragraphs(doc):
            if current and len(current) + len(para) > size:
                out.append(current)
                current = ''
            current = f"{current}\n\n{para}" if current else para
        if current:
            out.append(current)
    return [p for p in out if len(p) > size // 3]


def pick(chunks: list, names: list, source_lang: str, count: int) -> list:
    scored = []
    for i, chunk in enumerate(chunks):
        found = lexicon.find_terms(chunk, names, source_lang)
        if found:
            mentions = sum(chunk.count(n) for n in found)
            scored.append((-(mentions + len(_PRONOUNS.findall(chunk))), i))
    return sorted(i for _, i in sorted(scored)[:count])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('book', type=Path, help='исходник (.epub, .fb2, .txt, .md)')
    parser.add_argument('--dic', type=Path, required=True, help='словарь перевода (.dic)')
    parser.add_argument('--names', help='персонажи через запятую (по умолчанию — все с полом)')
    parser.add_argument('--count', type=int, default=8)
    parser.add_argument('--size', type=int, default=2000, help='длина отрывка, символов')
    parser.add_argument('--out', type=Path, required=True, help='JSON результата (рядом — .md)')
    parser.add_argument('--compare', type=Path, help='JSON прошлого прогона')
    args = parser.parse_args()

    config = utils.config
    entries = read_dic(args.dic)
    persons = [e for e in entries if e.category.upper() == 'PERSON' and e.gender in gender_check.GENDERS]
    names = ([n.strip() for n in args.names.split(',') if n.strip()] if args.names
             else [e.source for e in persons])
    if not names:
        sys.exit("В словаре нет персонажей с полом: заполните третье поле (he/she) или задайте --names")

    chunks = passages(args.book, args.size)
    chosen = pick(chunks, names, config.source_lang, args.count)
    print(f"{config.source_lang} -> {config.target_lang}, FAST_TRANS={config.fast_trans}, "
          f"GENDER_CHECK={config.gender_check}; отрывков: {len(chosen)} из {len(chunks)}")

    results = []
    for n, i in enumerate(chosen, 1):
        source = chunks[i]
        used = set(lexicon.find_terms(source, [e.source for e in entries], config.source_lang))
        vocab = [e for e in entries if e.source in used]
        started = time.time()
        translation, _ = utils.translate_chunk(
            source_lang=config.source_lang, target_lang=config.target_lang, source_text=source,
            outline_text='', vocab_dict={v.source: v.target for v in vocab}, vocab_entries=vocab,
            country=config.country, style='text', fast_mode=config.fast_trans)
        issues = gender_check.find_gender_issues(translation, vocab, config.target_lang)
        mixed = script_guard.find_mixed_words(translation, config.target_lang, [v.target for v in vocab])
        results.append({
            'index': i, 'seconds': round(time.time() - started, 1),
            'source': source, 'translation': translation, 'mixed_words': mixed,
            'gender_issues': [{'name': x.name, 'words': x.words,
                               'sentence': translation[x.start:x.end]} for x in issues],
        })
        print(f"[{n}/{len(chosen)}] отрывок {i}: смешанных слов {len(mixed)}, ошибок пола {len(issues)}, "
              f"{results[-1]['seconds']} с")

    pipeline = utils.metrics.get_report()
    summary = {
        'target_lang': config.target_lang, 'fast_trans': config.fast_trans,
        'gender_check': config.gender_check,
        'model_translate': config.model_translate, 'model_proofread': config.model_proofread,
        'passages': [r['index'] for r in results],
        'mixed_words_left': sum(len(r['mixed_words']) for r in results),
        'gender_issues_left': sum(len(r['gender_issues']) for r in results),
        'mixed_words_fixed_in_pipeline': pipeline['script_fixes'],
        'gender_issues_found_in_pipeline': pipeline['gender_issues'],
        'gender_issues_fixed_in_pipeline': pipeline['gender_fixed'],
        'seconds': round(sum(r['seconds'] for r in results), 1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False,
                                   indent=2), encoding='utf-8')
    md = args.out.with_suffix('.md')
    md.write_text('\n\n'.join(
        f"## Отрывок {r['index']}\n\n### Исходник\n\n{r['source']}\n\n### Перевод\n\n{r['translation']}"
        for r in results) + '\n', encoding='utf-8')

    previous = None
    if args.compare:
        previous = json.loads(args.compare.read_text(encoding='utf-8'))['summary']
        if previous.get('passages') != summary['passages']:
            print("ВНИМАНИЕ: отрывки другие, чем в сравниваемом прогоне — сравнение неточное")
    print()
    for key, value in summary.items():
        if key == 'passages':
            continue
        line = f"{key}: {value}"
        if previous is not None and isinstance(value, (int, float)) and not isinstance(value, bool) \
                and key in previous:
            line += f"  (было {previous[key]})"
        print(line)
    print(f"\nСохранено: {args.out}, переводы для чтения: {md}")


if __name__ == '__main__':
    main()
