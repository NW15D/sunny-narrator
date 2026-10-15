#!/usr/bin/env python3
"""Проверка категорий и пола в словаре .dic по исходнику книги, без LLM.

Пример:
    python scripts/review_dic.py books/eternal-moment.pg.epub --dic books/eternal-moment.pg.dic
    python scripts/review_dic.py books/Esher/rotj/The_Warship.epub --dic books/Esher/rotj/series.dic \\
        --min-votes 8 --ratio 0.9

Исходный словарь не меняется. Результат — `<имя>.reviewed.dic` рядом с ним
(или `-o`): те же строки, комментарии и порядок, изменены только поля, о
которых есть уверенные данные; отчёт со всеми доказательствами —
`<результат>.report.txt` (или `--report`). Проверьте отчёт и замените словарь.

Ошибочная категория тоже бьёт по полу: строка глоссария «Vorta = Ворта, PERSON»
подталкивает модель писать «Ворта сказала» о деревне; без пола модель угадывает
его в каждом чанке, а с полом стадия GENDER его ещё и проверяет.

Что проверяется (spaCy-модель исходного языка, NERMODEL или `--model`):
1. Категория — по меткам NER у вхождений записи в книге: PERSON/PER → PERSON,
   GPE/LOC/FAC → LOC, ORG → ORG. Меняется только связанное с персонажами:
   PERSON → LOC/ORG, TERM → PERSON, пустая → любая. Запись PERSON, которая в
   тексте пишется со строчной буквы (вид существ, обычное слово: «dracomen»),
   становится TERM.
2. Пол персонажа — по местоимениям 3-го лица единственного числа (род берётся
   из морфологии модели: he/him/his, she/her) в предложении, где назван только
   этот персонаж, и в следующем, если там не назван никто. Пустой пол
   заполняется; пол, который уже стоит в словаре и расходится с книгой, только
   попадает в отчёт. Записи, чья категория меняется в этом же прогоне, пол не
   ставится. Сигнал шумный: в сцене двух персонажей «she» в предложении о Kuno
   часто значит Vashti, поэтому пороги высокие — на демо-книге при них все
   проставленные полы верны, а спорные (Kuno he ×17 / she ×14) только в отчёте.
Решение принимается при `--min-votes` (5) и доле `--ratio` (0.85); слабее — в
отчёт. Для языков без рода местоимений (корейский, японский, китайский) пол
не определяется.
"""
import argparse
import collections
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.clean_dic import format_line, parse_dic, write_atomic  # noqa: E402
from src import lexicon, ner  # noqa: E402
from src.gender_check import normalize_gender  # noqa: E402
from src.vocabulary_manager import looks_like_proper_name  # noqa: E402

LABELS = {'PERSON': 'PERSON', 'PER': 'PERSON', 'GPE': 'LOC', 'LOC': 'LOC', 'FAC': 'LOC', 'ORG': 'ORG'}
FEATURE_GENDER = {'Masc': 'he', 'Fem': 'she'}
_BLOCK_END = re.compile(r'(?i)</(?:p|v|title|subtitle|h\d|li|div|blockquote)>|<br\s*/?>|<empty-line\s*/?>')


def book_paragraphs(book: Path) -> list:
    """Plain-text paragraphs of the book (ner.extract_text_from_book reads
    FB2, EPUB and TXT)."""
    body = _BLOCK_END.sub('\n\n', ner.extract_text_from_book(str(book)))
    text = html.unescape(re.sub(r'<[^>]+>', ' ', body))
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def read_rows(dic: Path) -> tuple:
    """(lines of the file, entries): the entries as clean_dic.parse_dic reads
    them, with the category upper-cased and the gender normalized for the
    decisions; a row is written back only when review() changed it."""
    lines = dic.read_text(encoding='utf-8-sig').splitlines()
    rows = parse_dic(dic, collections.defaultdict(list))
    for row in rows:
        row['category'] = row['category'].upper()
        row['gender'] = normalize_gender(row['gender'])
    return lines, rows


class Evidence:
    def __init__(self):
        self.labels = collections.Counter()   # mapped NER label of each mention
        self.mentions = 0
        self.lowercase = 0                    # mentions written lowercase (not sentence-initial)
        self.pronouns = collections.Counter()  # he / she


def collect(paragraphs: list, rows: list, nlp) -> dict:
    """Evidence per entry (by row index) from the book."""
    index = collections.defaultdict(list)  # first normalized token -> [(tokens, row idx)]
    for k, row in enumerate(rows):
        # the tokenizer of the book's text: "Mary-Ann" and "O'Brien" match
        words = [lexicon.normalize(t.text) for t in nlp.make_doc(row['source']) if not t.is_space]
        if words:
            index[words[0]].append((words, k))
    for cands in index.values():
        cands.sort(key=lambda c: -len(c[0]))  # the longest entry first
    evidence = collections.defaultdict(Evidence)

    for doc in nlp.pipe(paragraphs, batch_size=64):
        norm = [lexicon.normalize(t.text) for t in doc]
        mentions = []  # (start token, end token, row idx)
        i = 0
        while i < len(doc):
            hit = next(((words, k) for words, k in index.get(norm[i], ())
                        if norm[i:i + len(words)] == words), None)
            if hit is None:
                i += 1
                continue
            words, k = hit
            mentions.append((i, i + len(words), k))
            ev = evidence[k]
            ev.mentions += 1
            span = doc[i:i + len(words)]
            # "de la Vega" is a name: its particles are lowercase
            if not span[0].is_sent_start and not looks_like_proper_name(span.text):
                ev.lowercase += 1
            label = LABELS.get(span[-1].ent_type_)
            if label:
                ev.labels[label] += 1
            i += len(words)

        # gender: a sentence naming exactly one person, and the next one if it names nobody
        def is_person(k, start):
            return rows[k]['category'] == 'PERSON' or LABELS.get(doc[start].ent_type_) == 'PERSON'

        sents = list(doc.sents)
        named = []
        for sent in sents:
            people = {k for s, e, k in mentions if sent.start <= s < sent.end and is_person(k, s)}
            others = [ent for ent in sent.ents if LABELS.get(ent.label_) == 'PERSON'
                      and not any(ent.start <= s < ent.end for s, e, k in mentions)]
            named.append((people, bool(others)))
        for n, sent in enumerate(sents):
            people, others = named[n]
            if len(people) != 1 or others:
                continue
            k = next(iter(people))
            span = list(sent)
            if n + 1 < len(sents) and not named[n + 1][0] and not named[n + 1][1]:
                span += list(sents[n + 1])
            for tok in span:
                morph = tok.morph
                if (tok.pos_ == 'PRON' and 'Prs' in morph.get('PronType') and '3' in morph.get('Person')
                        and 'Sing' in morph.get('Number')):
                    for g in morph.get('Gender'):
                        if g in FEATURE_GENDER:
                            evidence[k].pronouns[FEATURE_GENDER[g]] += 1
    return evidence


def _majority(counter: collections.Counter, min_votes: int, ratio: float):
    """(winner, its votes, total) or None; winner only when it is sure."""
    total = sum(counter.values())
    if not total:
        return None
    winner, votes = counter.most_common(1)[0]
    return winner, votes, total, (total >= min_votes and votes / total >= ratio)


def review(rows: list, evidence: dict, min_votes: int, ratio: float, report: dict) -> int:
    """Apply the sure changes to rows; report everything. Returns the count."""
    changed = 0
    for k, row in enumerate(rows):
        ev = evidence.get(k)
        name = f"{row['source']} = {row['target']}"
        if ev is None or not ev.mentions:
            if row['category'] == 'PERSON' and not row['gender']:
                report['not found in the book'].append(name)
            continue
        old = row['category']

        # category
        new = None
        if old == 'PERSON' and ev.lowercase >= min_votes and ev.lowercase / ev.mentions >= ratio:
            new, why = 'TERM', f"lowercase in {ev.lowercase} of {ev.mentions} mentions"
        else:
            top = _majority(ev.labels, min_votes, ratio)
            if top and top[0] != old and (old in ('', 'TERM') and top[0] == 'PERSON'
                                          or old == 'PERSON' or old == ''):
                label, votes, total, sure = top
                why = f"NER {label} in {votes} of {total} tagged mentions ({ev.mentions} in all)"
                if sure:
                    new = label
                else:
                    report['category: not sure (not changed)'].append(f"{name}, {old or '—'}: {why}")
        if new:
            report['category changed'].append(f"{name}: {old or '—'} -> {new} ({why})")
            row['category'] = new
            row['changed'] = True
            changed += 1
            if new != 'PERSON' and row['gender']:
                report['gender cleared (not a person)'].append(f"{name}: {row['gender']}")
                row['gender'] = ''

        # gender
        if row['category'] != 'PERSON':
            continue
        top = _majority(ev.pronouns, min_votes, ratio)
        counts = ', '.join(f"{g} ×{n}" for g, n in ev.pronouns.most_common()) or 'no pronouns'
        if new and not row['gender']:  # a new person: one guess at a time, the gender waits
            report['gender not sure (not set)'].append(f"{name}: {counts} (category just changed)")
        elif top and top[3]:
            gender = top[0]
            if not row['gender']:
                report['gender set'].append(f"{name}: {gender} ({counts})")
                row['gender'] = gender
                row['changed'] = True
                changed += 1
            elif row['gender'] != gender:
                report['gender conflict (not changed)'].append(
                    f"{name}: the .dic says {row['gender']}, the book {gender} ({counts})")
        elif not row['gender']:
            report['gender not sure (not set)'].append(f"{name}: {counts}")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book', type=Path, help='исходник книги (.fb2, .epub, .txt)')
    ap.add_argument('--dic', type=Path, required=True, help='словарь .dic')
    ap.add_argument('-o', '--output', type=Path, help='результат (по умолчанию <имя>.reviewed.dic)')
    ap.add_argument('--report', type=Path, help='отчёт (по умолчанию <результат>.report.txt)')
    ap.add_argument('--model', default=ner.config.nermodel,
                    help=f'spaCy-модель исходного языка (по умолчанию {ner.config.nermodel})')
    ap.add_argument('--min-votes', type=int, default=5, help='минимум свидетельств для решения')
    ap.add_argument('--ratio', type=float, default=0.85, help='минимальная доля победителя')
    args = ap.parse_args()

    output = args.output or args.dic.with_name(f"{args.dic.stem}.reviewed.dic")
    report_path = args.report or output.with_name(f"{output.stem}.report.txt")
    if output.resolve() == args.dic.resolve():
        ap.error('результат не должен совпадать с исходным файлом')

    import spacy
    nlp = spacy.load(args.model)
    lines, rows = read_rows(args.dic)
    paragraphs = book_paragraphs(args.book)
    print(f"{len(rows)} entries, {len(paragraphs)} paragraphs, model {args.model}...")
    evidence = collect(paragraphs, rows, nlp)

    report = collections.defaultdict(list)
    changed = review(rows, evidence, args.min_votes, args.ratio, report)
    for row in rows:
        if row.get('changed'):  # the other lines stay as the user wrote them
            lines[row['line']] = format_line(row)
    write_atomic(output, '\n'.join(lines).rstrip('\n') + '\n')
    order = ['category changed', 'gender set', 'gender cleared (not a person)', 'gender conflict (not changed)',
             'category: not sure (not changed)', 'gender not sure (not set)', 'not found in the book']
    write_atomic(report_path, ''.join(f"## {k} ({len(report[k])})\n" + '\n'.join(report[k]) + '\n\n'
                                      for k in order if report.get(k)))
    print(f"{changed} change(s): {output}")
    for k in order:
        if report.get(k):
            print(f"  {k}: {len(report[k])}")
    print(f"report: {report_path}")


if __name__ == '__main__':
    main()
