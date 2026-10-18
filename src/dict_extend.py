"""
A dictionary carried over to the next book of a series or of an author's
universe (`app.py dict extend`): the entries the dictionary has stay as they
are, the new books (and other dictionaries) add what it lacks, and everything
is checked before the result is written.

    app.py dict extend series.dic --book vol3.epub [--book vol4.epub ...]
                                  [--books-dir DIR] [--merge other.dic ...] [-o DIR]

Sources of new entries:
- `--book` / `--books-dir`: NER over the new books (the counts are summed over
  all of them), the terms the proofread LLM translates; the category and the
  gender of a new entry come from the books (dict_review), not from the LLM;
- `--merge`: the entries of other dictionaries the base lacks.

What never becomes an entry: a candidate the dictionary already has (the same
entry in another case or form, or by the translated name of a character), a
phrase that contains a known term ("Jain node" when "Jain" is known: it would
only shadow "Jain" with another translation), an ordinary word of the language.
The same CandidateMatcher decides it as for the candidates of the synopsis
stage, the shorter term first, so the order of the lines does not matter. NER
reads the plain paragraphs of the books, not their markup. A merged entry that has another translation than the dictionary is a
conflict: the dictionary keeps its own, the conflict goes to the log.

The lines of the base file are copied as they are, the new entries follow
under one comment `# new words YYYY-MM-DD (sources)`, by category: every
extension leaves its own dated block at the end of the file. Only what dict review would do changes a base
line: an empty gender the books show clearly is set, and so is a category
dict review is sure about. A gender the books contradict, an unsure gender and
everything suspicious in the base (duplicates, ordinary words, cut variants)
is only reported.

The result goes to a folder (default `<dic>.extended/`): `<name>.dic` and
`<name>.extend.report.txt`, the log of what was added, skipped, changed and
what is disputed. The source .dic is not changed; both files are written only
after every step succeeded.
"""
import collections
import datetime
import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from src import dict_review, lexicon, ner
from src.dict_clean import (CATEGORY_ORDER, REPORT_EXT, drop_cut_variants, drop_ordinary_words,
                            format_line, normalize_fields, parse_dic, write_atomic)
from src.dict_review import MIN_VOTES, RATIO, read_rows
from src.vocabulary_manager import CandidateMatcher, VocabularyManager, min_word_length_for, term_chunks

logger = logging.getLogger(__name__)

# Order of the log: what needs a decision first, then what was done. The
# review sections are dict_review.review's own keys under the group prefix.
_GROUPS = ('base', 'merged', 'new')
_REVIEW_UNSURE = ('gender conflict (not changed)', 'category: not sure (not changed)',
                  'gender not sure (not set)')
_REVIEW_DONE = ('gender set', 'category changed', 'gender changed (the book disagrees)',
                'gender cleared (not a person)')
LOG_ORDER = (
    ['merge: conflict (the dictionary keeps its own translation)']
    + [f"{g}: {k}" for g in _GROUPS for k in _REVIEW_UNSURE]
    + ['check: translation in two alphabets', 'check: one translation for several entries',
       'check: translation equals the source', 'check: person without a gender', 'check: no books',
       'base: duplicate entries (not changed)', 'base: ordinary word (kept)', 'base: cut variant (kept)',
       'new: not translated by the LLM']
    + [f"{g}: {k}" for g in _GROUPS for k in _REVIEW_DONE]
    + ['added from books', 'added from dictionaries', 'skipped: already in the dictionary',
       'skipped: covered by existing terms', 'skipped: ordinary word',
       'skipped: same by the translated name', 'unknown gender (kept)']
    + [f"{g}: not found in the book" for g in _GROUPS]
)


def _norm(text: str) -> str:
    return lexicon.normalize(text).strip()


def _books_paragraphs(books: List[Path]) -> List[str]:
    """Plain paragraphs of all books: NER and the evidence read the same text,
    without the markup NER took for names (`href="https://...`, `I</subtitle`)."""
    paragraphs = []
    for book in books:
        paragraphs += dict_review.book_paragraphs(book)
    return paragraphs


def _translate(candidates: List[tuple], book: Path, source_lang: str, target_lang: str,
               country: str) -> List[dict]:
    """Entries for (term, category) candidates: the proofread LLM translates,
    the category stays NER's (VocabularyManager._parse_and_append_chunk with
    `categories`, as build_dictionary does)."""
    from src import utils as ta
    if not candidates:
        return []
    categories = {term: cat for term, cat in candidates}
    lines = [f"{term} [{cat}]" if cat else term for term, cat in candidates]
    chunks = term_chunks(lines)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'translated.dic'
        path.write_text('', encoding='utf-8')
        manager = VocabularyManager(str(book), dict_file=str(path), source_lang=source_lang,
                                    target_lang=target_lang, country=country)
        for idx, chunk in enumerate(chunks, 1):
            logger.info(f"Translating chunk {idx}/{len(chunks)} ({len(chunk)} chars)...")
            answer = ta.vocabulary(source_lang, target_lang, chunk, country, "proofread")
            manager._parse_and_append_chunk(answer, idx, len(chunks), out_path=str(path),
                                            categories=categories)
        return parse_dic(path, collections.defaultdict(list))


def _evidence_slice(evidence: dict, start: int, stop: int) -> dict:
    return {k - start: ev for k, ev in evidence.items() if start <= k < stop}


def _add(log: dict, prefix: str, report: dict):
    for key, lines in report.items():
        log[f"{prefix}: {key}"] += lines


def _render_new(rows: List[dict], label: str) -> List[str]:
    """The new entries under one dated comment, so the file shows which lines
    an extension added; by category, without sub-headings."""
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    rows = sorted(rows, key=lambda r: order.get(r['category'], len(order)))
    return ['', f"# new words {datetime.date.today().isoformat()} ({label})"] + [format_line(r) for r in rows]


def _log_keys(log: dict) -> List[str]:
    return [k for k in LOG_ORDER if log.get(k)] + sorted(k for k in log if k not in LOG_ORDER and log[k])


def extend_file(dic: Path, books: List[Path] = (), merges: List[Path] = (), output_dir: Path = None,
                model: str = None, min_count_ner: int = 3, min_count_word: int = 5,
                include_words: Optional[bool] = None, keep: str = '',
                min_votes: int = MIN_VOTES, ratio: float = RATIO) -> dict:
    """`app.py dict extend`: see the module docstring. Returns {'output', 'report',
    'base', 'added', 'changed', 'counts'}; the languages and the LLM come from
    the configuration (.env)."""
    books, merges = list(books), list(merges)
    if not books and not merges:
        raise ValueError('nothing to extend the dictionary with: give --book, --books-dir or --merge')
    for path in [dic] + books + merges:
        if not path.exists():
            raise ValueError(f"file not found: {path}")
    config = ner.config
    output_dir = output_dir or dic.with_name(f"{dic.stem}.extended")
    output = output_dir / dic.name
    report_path = output_dir / f"{dic.stem}.extend{REPORT_EXT}"
    inputs = {p.resolve() for p in [dic] + books + merges}
    if output.resolve() in inputs or report_path.resolve() in inputs:
        raise ValueError('the result must not overwrite an input file: choose another folder')
    previous_model = config.nermodel
    if model:
        config.nermodel = model
    try:
        return _extend(dic, books, merges, output_dir, output, report_path, config, keep,
                       min_count_ner, min_count_word, include_words, min_votes, ratio)
    finally:
        config.nermodel = previous_model


def _extend(dic, books, merges, output_dir, output, report_path, config, keep,
            min_count_ner, min_count_word, include_words, min_votes, ratio) -> dict:
    source_lang, target_lang, country = config.source_lang, config.target_lang, config.country
    keep = {w.strip().casefold() for w in keep.split(',') if w.strip()}

    log = collections.defaultdict(list)
    lines, base = read_rows(dic)
    matcher = CandidateMatcher(source_lang)
    for row in base:
        matcher.add(row['source'], row['target'], row)

    # --- the base: only reported -------------------------------------------
    groups = collections.defaultdict(list)
    for row in base:
        groups[lexicon.word_key(row['source'])].append(row)
    for group in groups.values():
        if len(group) > 1:
            log['base: duplicate entries (not changed)'].append(
                ' | '.join(f"{r['source']} = {r['target']}" for r in group))
    suspicious = collections.defaultdict(list)
    _, ordinary = drop_ordinary_words(base, keep, suspicious)
    drop_cut_variants(base, ordinary, suspicious)
    _add(log, 'base', {'ordinary word (kept)': suspicious['ordinary word'],
                       'cut variant (kept)': suspicious['cut variant']})

    # --- other dictionaries --------------------------------------------------
    # the shorter term first in every source: "Jain" added before "Jain tech"
    # covers it, whatever the order of the lines (vocabulary_manager._by_priority)
    incoming = []
    for other in merges:
        for row in read_rows(other)[1]:
            normalize_fields(row, log)
            incoming.append((other, row))
    incoming.sort(key=lambda item: lexicon.term_rank(item[1]['source']))
    merged = []
    for other, row in incoming:
        cand = {'source': row['source'], 'target': row['target'],
                'category': row['category'] or 'TERM'}
        kind, ref = matcher.match(cand)
        name = f"{row['source']} = {row['target']}"
        if kind == 'same':
            if _norm(ref['target']) == _norm(row['target']):
                log['skipped: already in the dictionary'].append(f"{name} ({other.name})")
            else:
                log['merge: conflict (the dictionary keeps its own translation)'].append(
                    f"{row['source']}: the dictionary has {ref['source']} = {ref['target']}, "
                    f"{other.name} has {row['target']}")
        elif kind == 'covered':
            log['skipped: covered by existing terms'].append(
                f"{name} ({other.name}): contains {', '.join(ref)}")
        else:
            row['origin'] = other.name
            merged.append(row)
            matcher.add(row['source'], row['target'], row)
            log['added from dictionaries'].append(f"{name} ({other.name})")

    # --- the books --------------------------------------------------------------
    new, paragraphs = [], []
    if books:
        paragraphs = _books_paragraphs(books)
        found = ner.create_dictionary_from_text(
            '\n\n'.join(paragraphs), min_count_ner=min_count_ner, min_count_word=min_count_word,
            include_words=include_words, min_word_length=min_word_length_for(source_lang),
            lang=source_lang)
        lowercase = [t for t, _, _ in found if t == t.lower() and t.casefold() not in keep]
        common = ner.known_words(lowercase)
        fresh, keys = [], set()
        for term, category, _ in sorted(found, key=lambda f: lexicon.term_rank(f[0])):
            if term in common:
                log['skipped: ordinary word'].append(term)
                continue
            kind, ref = matcher.match({'source': term, 'category': category})
            if kind == 'same':
                log['skipped: already in the dictionary'].append(f"{term} = {ref['target']}")
            elif kind == 'covered':
                log['skipped: covered by existing terms'].append(f"{term}: contains {', '.join(ref)}")
            elif lexicon.word_key(term) not in keys:  # one request per entry
                keys.add(lexicon.word_key(term))
                fresh.append((term, category))
        translated = _translate(fresh, books[0], source_lang, target_lang, country)
        translated.sort(key=lambda r: lexicon.term_rank(r['source']))
        got = {r['source'].casefold() for r in translated}
        log['new: not translated by the LLM'] += [t for t, _ in fresh if t.casefold() not in got]
        for row in translated:
            row['origin'] = 'books'
            kind, ref = matcher.match({'source': row['source'], 'target': row['target'],
                                       'category': row['category'] or 'TERM'})
            if kind == 'same':
                log['skipped: same by the translated name'].append(
                    f"{row['source']} = {row['target']} (is {ref['source']})")
            elif kind == 'covered':
                log['skipped: covered by existing terms'].append(
                    f"{row['source']}: contains {', '.join(ref)}")
            else:
                new.append(row)
                matcher.add(row['source'], row['target'], row)
                log['added from books'].append(f"{row['source']} = {row['target']}, {row['category']}")

    # --- categories and genders by the books, as dict review does -------------------
    if paragraphs:
        # the model NER has just used (no second copy in memory), unless it
        # has nothing that splits sentences: dict_review adds a sentencizer
        nlp = ner._get_nlp(config.nermodel)
        if not ({'parser', 'senter', 'sentencizer'} & set(nlp.pipe_names)):
            nlp = dict_review._load_model(config.nermodel)
        if nlp is None:
            raise RuntimeError(f"spaCy model {config.nermodel} is not installed")
        everything = base + merged + new
        evidence = dict_review.collect(paragraphs, everything, nlp)
        start = 0
        for prefix, rows, promote in (('base', base, False), ('merged', merged, False), ('new', new, True)):
            report = collections.defaultdict(list)
            dict_review.review(rows, _evidence_slice(evidence, start, start + len(rows)),
                                          min_votes, ratio, report, promote_persons=promote)
            _add(log, prefix, report)
            start += len(rows)
    else:
        log['check: no books'].append('categories and genders were not checked against a book')

    # --- the checks of the whole result ---------------------------------------------
    result = base + merged + new
    check = collections.defaultdict(list)
    dict_review._mixed_translations(result, target_lang, check)
    _add(log, 'check', check)
    by_target = collections.defaultdict(list)
    for row in result:
        by_target[_norm(row['target'])].append(row)
    for rows in by_target.values():
        if len({lexicon.word_key(r['source']) for r in rows}) > 1:
            log['check: one translation for several entries'].append(
                ' | '.join(f"{r['source']} = {r['target']}" for r in rows))
    for row in new + merged:
        if row['category'] == 'TERM' and _norm(row['source']) == _norm(row['target']):
            log['check: translation equals the source'].append(f"{row['source']} = {row['target']}")
    for row in result:
        if row['category'] == 'PERSON' and not row['gender']:
            log['check: person without a gender'].append(f"{row['source']} = {row['target']}")

    # --- the result -------------------------------------------------------------------------
    for row in base:
        if row.get('changed'):  # the other lines stay as the user wrote them
            lines[row['line']] = format_line(row)
    added = merged + new
    if added:
        label = ', '.join([b.name for b in books] + [m.name for m in merges])
        lines += _render_new(added, label)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(output, '\n'.join(lines).rstrip('\n') + '\n')
    summary = [f"base: {dic.name}, {len(base)} entries",
               f"books: {', '.join(b.name for b in books) or '-'}",
               f"dictionaries: {', '.join(m.name for m in merges) or '-'}",
               f"added: {len(added)} ({len(new)} from books, {len(merged)} from dictionaries)",
               f"changed in the base: {sum(1 for r in base if r.get('changed'))}"]
    dict_review._write_report(report_path, log, f"# dict extend: {dic.name}\n" + '\n'.join(summary),
                              order=_log_keys(log))
    return {'output': output, 'report': report_path, 'base': len(base), 'added': len(added),
            'changed': sum(1 for r in base if r.get('changed')),
            'counts': {k: len(log[k]) for k in _log_keys(log)}}
