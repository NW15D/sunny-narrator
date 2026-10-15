"""
The dictionary checked against the source book, without an LLM: before every
translation (preflight, from VocabularyManager.initialize) and as
`app.py dict review`.

A wrong category hits the gender too: "Vorta = Ворта, PERSON" makes the model
write "Ворта сказала" of a village; without a gender the model guesses it in
every chunk, and the GENDER stage checks the translation against the .dic.

What is checked (the spaCy model of the source language, NERMODEL):
1. Category, by the NER labels of the entry's mentions in the book
   (PERSON/PER -> PERSON, GPE/LOC/FAC -> LOC, ORG -> ORG). Only what concerns
   characters changes: PERSON -> LOC/ORG (only if the book never calls it
   he/she: NER tags invented names ORG - Trike, Cog, the Client), TERM ->
   PERSON, empty -> any. A PERSON written lowercase in the .dic (a species,
   "dracomen") that the book writes lowercase too becomes TERM. A lowercase
   word is not a mention of a capitalized name ("stone" is not "Stone").
2. Gender of a character, by the 3rd person singular pronouns (their gender
   from the model's morphology: he/him/his, she/her) of the sentences naming
   only this character, and of the next one if it names nobody. In a scene of
   two the signal is noisy ("she" next to Kuno is often Vashti), so a decision
   needs MIN_VOTES pronouns and RATIO of them for one gender; less goes to the
   report. Languages without gendered pronouns (ko, ja, zh) get no gender.

Before a translation (DICT_CHECK, on by default) the sure findings - an empty
gender, a gender the book contradicts, a category - are applied to the
dictionary in memory for the run (DICT_AUTOFIX, on by default; --no-autofix
turns it off): the .dic stays as it is, `<dic>.reviewed.dic` gets them for the
user to take. Without autofix a contradiction stops the run (--force goes on).
A translation of an entry written in two alphabets is reported. What the book
says of each entry is cached (`<book>.dictcheck.json`): a resumed run, or one
after editing a category or gender, does not parse the book again, only a new
entry does; the decisions are made every run. The report is
`<book>.dictcheck.txt`.
"""
import collections
import hashlib
import html
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from src import lexicon, ner, script_guard
from src.dict_clean import REPORT_EXT, format_line, parse_dic, write_atomic
from src.gender_check import normalize_gender

logger = logging.getLogger(__name__)

# NER labels -> the categories a review decides between (ner.CATEGORY_OF_LABEL,
# the table the dictionary is built with; its TERM labels are left out: a
# review moves entries only between people, places and organizations)
LABELS = {label: cat for label, cat in ner.CATEGORY_OF_LABEL.items() if cat != 'TERM'}
FEATURE_GENDER = {'Masc': 'he', 'Fem': 'she'}
THIRD_PERSON = {'3', 'Third'}  # en/de/fr/...: "3", ru: "Third"
# Forms of address that tell a gender: in the entry ("Miss Raby", "Signora
# Cantù") or before the name in the book ("Miss Harbottle"). Far more reliable
# than pronouns: "Harbottle, who was always right, had warned me against
# him" is about another man. Normalized (casefold), without the dot.
HONORIFICS = {
    'he': {'mr', 'sir', 'lord', 'master', 'mister', 'signor', 'monsieur', 'herr', 'señor', 'senhor',
           'don', 'dom', 'pan', 'pane', 'господин', 'мистер', 'сэр', 'лорд', 'пан', 'синьор', 'месье',
           'герр', 'сеньор'},
    'she': {'mrs', 'miss', 'ms', 'lady', 'madam', 'madame', 'mademoiselle', 'mme', 'mlle', 'signora',
            'signorina', 'frau', 'fräulein', 'señora', 'señorita', 'senhora', 'dona', 'doña', 'pani',
            'госпожа', 'миссис', 'мисс', 'леди', 'мадам', 'мадемуазель', 'синьора', 'синьорина', 'фрау',
            'сеньора', 'сеньорита'},
}
_HONORIFIC = {word: gender for gender, words in HONORIFICS.items() for word in words}


def honorific_gender(source: str) -> Optional[str]:
    """he/she when the entry starts with a form of address ("Miss Raby")."""
    words = lexicon.tokenize(source)
    return _HONORIFIC.get(words[0]) if len(words) > 1 else None


# Pronouns of languages whose models give them no gender feature
PRONOUN_GENDER = {
    'zh': {'他': 'he', '她': 'she'},
    'ja': {'彼': 'he', '彼女': 'she'},
    'ko': {'그녀': 'she', '그녀가': 'she', '그녀는': 'she', '그녀의': 'she', '그녀를': 'she',
           '그는': 'he', '그가': 'he', '그의': 'he', '그를': 'he'},
}
# "More than three" mismatches of the book with the .dic decide, with this
# share of the evidence for one side
MIN_VOTES = 4
RATIO = 0.85
# The reports the dictionary tools leave next to the books and dictionaries:
# never a book (ner.series_book_files)
REPORT_SUFFIX = '.dictcheck.txt'
GENERATED_SUFFIXES = (REPORT_SUFFIX, REPORT_EXT)
REPORT_ORDER = ['category changed', 'gender changed (the book disagrees)', 'gender set',
                'gender cleared (not a person)', 'gender conflict (not changed)',
                'translation in two alphabets', 'category: not sure (not changed)',
                'gender not sure (not set)', 'not found in the book']
# what a translation must not start with when nothing fixes it
ERRORS = ('category changed', 'gender changed (the book disagrees)', 'gender conflict (not changed)',
          'translation in two alphabets')

_BLOCK_END = re.compile(r'(?i)</(?:p|v|title|subtitle|h\d|li|div|blockquote)>|<br\s*/?>|<empty-line\s*/?>')
_MD_LINE_MARK = re.compile(r'(?m)^[ \t]*(?:#{1,6}|>|[*+-]|\d+[.)])[ \t]+')
_MD_EMPHASIS = re.compile(r'[*_]{1,3}')


def text_paragraphs(text: str) -> List[str]:
    """Plain paragraphs of a book's text: FB2/HTML (tags dropped, entities
    resolved) or Markdown (marks, links and placeholders dropped)."""
    text = _BLOCK_END.sub('\n\n', text or '')
    text = ' '.join(lexicon.text_segments(text))
    text = _MD_EMPHASIS.sub('', _MD_LINE_MARK.sub('', html.unescape(text)))
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def book_paragraphs(book: Path) -> List[str]:
    """Plain paragraphs of a FB2, EPUB or TXT book (ner.extract_text_from_book)."""
    return text_paragraphs(ner.extract_text_from_book(str(book)))


def read_rows(dic: Path) -> tuple:
    """(lines of the file, entries): the entries as dict_clean.parse_dic reads
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
        self.honorifics = collections.Counter()  # he / she: "Miss" before the name


def looks_like_proper_name(source: str) -> bool:
    # vocabulary_manager imports this module lazily: no import cycle
    from src.vocabulary_manager import looks_like_proper_name as proper
    return proper(source)


def _pronoun_gender(tok, lexical: dict) -> Optional[str]:
    """he/she of a 3rd person singular personal pronoun: by the model's
    morphology, or by `lexical` for the languages without it (zh, ja, ko)."""
    if tok.pos_ != 'PRON':
        return None
    morph = tok.morph
    if morph.get('Gender'):
        if (set(morph.get('Person')) & THIRD_PERSON and 'Sing' in morph.get('Number')
                and 'Prs' in (morph.get('PronType') or ['Prs'])):
            for g in morph.get('Gender'):
                if g in FEATURE_GENDER:
                    return FEATURE_GENDER[g]
        return None
    return lexical.get(tok.text)


def collect(paragraphs: list, rows: list, nlp) -> dict:
    """Evidence per entry (by row index) from the book."""
    lexical = PRONOUN_GENDER.get(nlp.lang, {})
    index = collections.defaultdict(list)  # first normalized token -> [(tokens, row idx)]
    proper = [looks_like_proper_name(row['source']) for row in rows]
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
            span = doc[i:i + len(words)]
            # "de la Vega" is a name: its particles are lowercase
            lowercase = not span[0].is_sent_start and not looks_like_proper_name(span.text)
            if proper[k] and lowercase:
                i += 1  # "stone" is another word than the name "Stone"
                continue
            mentions.append((i, i + len(words), k))
            ev = evidence[k]
            ev.mentions += 1
            j = i - 1
            if j >= 0 and doc[j].text == '.':
                j -= 1  # "Mr . Andrews" split by a tokenizer
            title = norm[j].rstrip('.') if j >= 0 else ''  # English keeps "Mr." one token
            if title in _HONORIFIC:
                ev.honorifics[_HONORIFIC[title]] += 1
            if lowercase:
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
                gender = _pronoun_gender(tok, lexical)
                if gender:
                    evidence[k].pronouns[gender] += 1
    return evidence


def _majority(counter: collections.Counter, min_votes: int, ratio: float):
    """(winner, its votes, total) or None; winner only when it is sure."""
    total = sum(counter.values())
    if not total:
        return None
    winner, votes = counter.most_common(1)[0]
    return winner, votes, total, (total >= min_votes and votes / total >= ratio)


def review(rows: list, evidence: dict, min_votes: int, ratio: float, report: dict,
           fix_conflicts: bool = False, promote_persons: bool = False) -> int:
    """Apply the sure changes to rows; report everything. Returns the count.
    A gender the .dic has and the book contradicts is changed only with
    `fix_conflicts` (the check before a translation), otherwise reported.
    `promote_persons` (a dictionary just built from NER): a capitalized entry
    the book keeps calling he or she becomes a PERSON with that gender,
    whatever NER tagged it ("Trike" ORG); a reviewed dictionary is the
    user's, its LOC/ORG stay."""
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
        # someone the book keeps calling he (or she) in the sentences naming
        # only them is a person, whatever NER says (it tags invented names
        # ORG: Trike, Cog); mixed pronouns are other people around a place
        pronouns = sum(ev.pronouns.values())
        person = _majority(ev.pronouns, min_votes, ratio)
        if (old == 'PERSON' and not looks_like_proper_name(row['source'])
                and ev.lowercase >= min_votes and ev.lowercase / ev.mentions >= ratio):
            new, why = 'TERM', f"lowercase in {ev.lowercase} of {ev.mentions} mentions"
        elif promote_persons and old in ('PERSON', 'LOC', 'ORG') and not looks_like_proper_name(row['source']):
            # NER tagged a lowercase word ("dell", "submind"): not a name
            new, why = 'TERM', "a lowercase word, not a name"
        elif (promote_persons and old != 'PERSON' and person and person[3]
              and looks_like_proper_name(row['source'])):
            new, why = 'PERSON', f"the book calls it {person[0]} ({person[1]} of {pronouns} pronouns)"
        else:
            top = _majority(ev.labels, min_votes, ratio)
            if top and top[0] != old and (old in ('', 'TERM') and top[0] == 'PERSON'
                                          or old == 'PERSON' or old == ''):
                label, votes, total, sure = top
                why = f"NER {label} in {votes} of {total} tagged mentions ({ev.mentions} in all)"
                if sure and old == 'PERSON' and person and person[3]:
                    why += f"; but the book calls it {person[0]} ({person[1]} of {pronouns} pronouns)"
                    sure = False
                elif (sure and old == 'PERSON' and not promote_persons
                      and (pronouns >= min_votes or row['gender'])):
                    # the user's dictionary says person: he/she around the name
                    # (as much evidence as any decision) or a gender set by
                    # hand keeps it one
                    why += (f"; but the .dic has a gender ({row['gender']})" if row['gender']
                            else f"; but he/she in {pronouns} sentence(s) naming only it")
                    sure = False
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

        # gender: a form of address in the entry or before the name (2+, one
        # gender) decides; else the pronouns
        if row['category'] != 'PERSON':
            continue
        titled = honorific_gender(row['source'])
        if titled is None and sum(ev.honorifics.values()) >= 2 and len(ev.honorifics) == 1:
            titled = next(iter(ev.honorifics))
        top = (titled, 1, 1, True) if titled else _majority(ev.pronouns, min_votes, ratio)
        if not titled and top and top[3] and ev.honorifics and top[0] not in ev.honorifics:
            top = (top[0], top[1], top[2], False)  # "Miss Harbottle" once, "he" around her: unsure
        counts = ', '.join(f"{g} ×{n}" for g, n in ev.pronouns.most_common()) or 'no pronouns'
        if titled:
            counts = f"form of address: {titled}; pronouns: {counts}"
        if new and not row['gender'] and not why.startswith('the book calls it'):
            # a person by NER labels only: one guess at a time, the gender waits
            report['gender not sure (not set)'].append(f"{name}: {counts} (category just changed)")
        elif top and top[3]:
            gender = top[0]
            if not row['gender']:
                report['gender set'].append(f"{name}: {gender} ({counts})")
                row['gender'] = gender
                row['changed'] = True
                changed += 1
            elif row['gender'] != gender:
                if fix_conflicts:
                    report['gender changed (the book disagrees)'].append(
                        f"{name}: {row['gender']} -> {gender} ({counts})")
                    row['gender'] = gender
                    row['changed'] = True
                    changed += 1
                else:
                    report['gender conflict (not changed)'].append(
                        f"{name}: the .dic says {row['gender']}, the book {gender} ({counts})")
        elif not row['gender']:
            report['gender not sure (not set)'].append(f"{name}: {counts}")
    return changed


def _mixed_translations(rows: list, target_lang: str, report: dict):
    for row in rows:
        words = script_guard.find_mixed_words(row['target'], target_lang)
        if words:
            report['translation in two alphabets'].append(f"{row['source']} = {row['target']}")


def _write_report(path: Path, report: dict, title: str = ''):
    text = (title + '\n\n' if title else '') + ''.join(
        f"## {k} ({len(report[k])})\n" + '\n'.join(report[k]) + '\n\n'
        for k in REPORT_ORDER if report.get(k))
    write_atomic(path, text)


def _write_reviewed(dic: Path, output: Path, changed_rows: list):
    """`dic` with the changed rows rewritten, every other line as it was."""
    lines, rows = read_rows(dic)
    by_source = {r['source']: r for r in changed_rows}
    for row in rows:
        new = by_source.get(row['source'])
        if new:
            lines[row['line']] = format_line(dict(row, category=new['category'], gender=new['gender']))
    write_atomic(output, '\n'.join(lines).rstrip('\n') + '\n')


def _load_model(name: str):
    """The source language model; one without a parser (xx_ent_wiki_sm) gets
    a sentencizer, the gender evidence is per sentence."""
    try:
        import spacy
        nlp = spacy.load(name)
        if not ({'parser', 'senter', 'sentencizer'} & set(nlp.pipe_names)):
            nlp.add_pipe('sentencizer')
        return nlp
    except Exception as e:
        logger.warning(f"Dictionary check skipped: spaCy model '{name}' is not available ({e}); "
                       f"python -m spacy download {name}")
        return None


def review_file(book: Path, dic: Path, output: Path = None, report_path: Path = None,
                model: str = None, min_votes: int = MIN_VOTES, ratio: float = RATIO,
                target_lang: str = '') -> dict:
    """`app.py dict review`: the sure findings into `output` (default
    <name>.reviewed.dic, only the changed lines), everything with the
    evidence into the report. The source .dic is not changed; a gender the
    book contradicts is only reported here."""
    output = output or dic.with_name(f"{dic.stem}.reviewed.dic")
    report_path = report_path or output.with_name(f"{output.stem}{REPORT_EXT}")
    if output.resolve() == dic.resolve():
        raise ValueError('the result must not overwrite the source file')
    model = model or ner.config.nermodel
    nlp = _load_model(model)
    if nlp is None:
        raise RuntimeError(f"spaCy model {model} is not installed")
    lines, rows = read_rows(dic)
    paragraphs = book_paragraphs(book)
    evidence = collect(paragraphs, rows, nlp)
    report = collections.defaultdict(list)
    changed = review(rows, evidence, min_votes, ratio, report)
    if target_lang:
        _mixed_translations(rows, target_lang, report)
    for row in rows:
        if row.get('changed'):  # the other lines stay as the user wrote them
            lines[row['line']] = format_line(row)
    write_atomic(output, '\n'.join(lines).rstrip('\n') + '\n')
    _write_report(report_path, report)
    return {'output': output, 'report': report_path, 'entries': len(rows),
            'paragraphs': len(paragraphs), 'changed': changed,
            'counts': {k: len(report[k]) for k in REPORT_ORDER if report.get(k)}}


class DictionaryCheckFailed(Exception):
    """The dictionary contradicts the book and autofix is off (--no-autofix)."""
    def __init__(self, report_path, errors: int):
        self.report_path, self.errors = report_path, errors
        super().__init__(f"The dictionary contradicts the book in {errors} place(s): see {report_path}. "
                         f"Fix the .dic, run without --no-autofix, or add --force.")


def _best_effort(write, *args, **kwargs):
    """A file of the check (report, reviewed copy) that cannot be written
    (a read-only series dictionary, a shared mount) never stops the run:
    the fixes are applied in memory anyway."""
    try:
        write(*args, **kwargs)
        return True
    except OSError as e:
        logger.warning(f"Dictionary check: {args[0] if args else ''} not written ({e})")
        return False


def reviewed_path(manager) -> Path:
    """Where the check puts the fixed copy of the dictionary: next to it,
    `<dic>.reviewed.dic`; for a dictionary shared by a series (its name is
    not the book's) `<dic>.<book>.reviewed.dic`, so the books of the series do
    not overwrite each other's findings."""
    dic = Path(manager.dict_file)
    if dic.stem == manager.book_name:
        return dic.with_name(f"{dic.stem}.reviewed.dic")
    return dic.with_name(f"{dic.stem}.{manager.book_name}.reviewed.dic")


_EVIDENCE_FIELDS = ('labels', 'pronouns', 'honorifics')


def _book_key(source_text: str, model: str) -> str:
    return hashlib.sha256(json.dumps([model, MIN_VOTES, RATIO]).encode('utf-8')
                          + hashlib.sha256(source_text.encode('utf-8')).digest()).hexdigest()


def _entries_key(rows: list) -> list:
    """What collect() depends on besides the book: the entries (longer ones
    take mentions from shorter ones) and their categories (a PERSON is
    counted in the pronoun scenes)."""
    return sorted([lexicon.word_key(r['source']), r['category']] for r in rows)


def _save_evidence(cache_path: Path, source_text: str, model: str, rows: list, evidence: dict):
    """What the book says of each entry (by its source), not the decisions:
    an edited gender reuses it; a new or removed entry or a changed category
    parses the book again."""
    data = {lexicon.word_key(row['source']): {
        'mentions': ev.mentions, 'lowercase': ev.lowercase,
        **{f: dict(getattr(ev, f)) for f in _EVIDENCE_FIELDS}}
        for k, row in enumerate(rows) for ev in [evidence.get(k, Evidence())]}
    write_atomic(cache_path, json.dumps({'book': _book_key(source_text, model), 'entries': _entries_key(rows),
                                         'evidence': data}, ensure_ascii=False))


def _cached_evidence(cache_path: Path, source_text: str, model: str, rows: list) -> Optional[dict]:
    """The evidence per row index from the cache, or None when the book, the
    model or any entry (a new one) is not in it."""
    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if cached.get('book') != _book_key(source_text, model) or cached.get('entries') != _entries_key(rows):
        return None
    stored = cached.get('evidence', {})
    evidence = {}
    for k, row in enumerate(rows):
        item = stored.get(lexicon.word_key(row['source']))
        if item is None:
            return None
        ev = Evidence()
        ev.mentions, ev.lowercase = item['mentions'], item['lowercase']
        for f in _EVIDENCE_FIELDS:
            getattr(ev, f).update(item.get(f, {}))
        evidence[k] = ev
    return evidence


def _rows_of(vocab: dict) -> list:
    return [{'key': key, 'source': e.source, 'target': e.target, 'category': (e.category or '').upper(),
             'gender': normalize_gender(e.gender), 'notes': e.notes} for key, e in vocab.items()]


def preflight(manager, source_text: Optional[str], config, write_back: bool = False) -> dict:
    """See _check; write_back: the dictionary was just built by NER (not
    reviewed by anyone): the findings go into its file, and an entry the book
    keeps calling he/she becomes a PERSON whatever NER tagged it."""
    return _check(manager, source_text, config, write_back)


def _check(manager, source_text: Optional[str], config, write_back: bool) -> dict:
    """
    The check before a translation (see the module docstring). `manager` is
    the loaded VocabularyManager, `source_text` the book (FB2 body or the
    Calibre pipeline's Markdown; None: parsed from manager.book_path).
    write_back: a dictionary just built (--build-dict or a missing .dic) gets
    the fixes into its own file, as nobody has reviewed it yet.

    Returns {'fixes': [...], 'errors': n, 'report': path} ({} when skipped).
    Raises DictionaryCheckFailed without autofix when the dictionary
    contradicts the book, unless config.dict_force.
    """
    if not getattr(config, 'dict_check', True) or not manager.vocab:
        return {}
    if source_text is None:
        try:
            source_text = ner.extract_text_from_book(manager.book_path)
        except Exception as e:
            logger.warning(f"Dictionary check skipped: the book text is not available ({e})")
            return {}
    autofix = getattr(config, 'dict_autofix', True)
    rows = _rows_of(manager.vocab)
    book_dir = Path(manager.book_dir or '.')
    cache_path = book_dir / f"{manager.book_name}.dictcheck.json"
    report_path = book_dir / f"{manager.book_name}{REPORT_SUFFIX}"
    model = config.nermodel
    evidence = _cached_evidence(cache_path, source_text, model, rows)
    if evidence is None:
        nlp = _load_model(model)
        if nlp is None:
            return {}
        paragraphs = text_paragraphs(source_text)
        logger.info(f"Dictionary check: {len(rows)} entries against {len(paragraphs)} paragraphs "
                    f"of the book ({model})...")
        evidence = collect(paragraphs, rows, nlp)
        _best_effort(_save_evidence, cache_path, source_text, model, rows, evidence)
    else:
        logger.info(f"Dictionary check: the evidence of this book is cached ({cache_path.name})")

    # the decisions are cheap: made again every run, from the dictionary as it is now
    report = collections.defaultdict(list)
    originals = {r['key']: (r['category'], r['gender']) for r in rows}
    review(rows, evidence, MIN_VOTES, RATIO, report, fix_conflicts=True, promote_persons=write_back)
    _mixed_translations(rows, manager.target_lang, report)
    fixes = [{'key': r['key'], 'source': r['source'], 'category': r['category'], 'gender': r['gender'],
              'was': list(originals[r['key']])} for r in rows if r.get('changed')]
    errors = sum(len(report[k]) for k in ERRORS if report.get(k))
    _best_effort(_write_report, report_path, report,
                 title=f"Dictionary {manager.dict_file} against {manager.book_path}")
    result = {'fixes': fixes, 'errors': errors,
              'counts': {k: len(report[k]) for k in REPORT_ORDER if report.get(k)}}

    fixes, errors = result['fixes'], result['errors']
    summary = ', '.join(f"{k}: {n}" for k, n in result['counts'].items()) or 'nothing found'
    if autofix or write_back:
        for fix in fixes:
            entry = manager.vocab.get(fix['key'])
            if entry is not None:
                entry.category, entry.gender = fix['category'], fix['gender']
        if fixes:
            manager.apply_review_fixes()
            if write_back:
                written = _best_effort(_write_reviewed, Path(manager.dict_file), Path(manager.dict_file), fixes)
                where = (f"written into {manager.dict_file}" if written else
                         f"for this run only: {manager.dict_file} could not be written")
            else:
                reviewed = reviewed_path(manager)
                written = _best_effort(_write_reviewed, Path(manager.dict_file), reviewed, fixes)
                where = f"for this run; {Path(manager.dict_file).name} is unchanged" + (
                    f", {reviewed.name} has them" if written else "")
            logger.warning(f"Dictionary check: {len(fixes)} fix(es) applied {where}. Report: {report_path}")
            for fix in fixes:
                logger.info(f"  {fix['source']}: {'/'.join(x or '—' for x in fix['was'])} -> "
                            f"{fix['category'] or '—'}/{fix['gender'] or '—'}")
        logger.info(f"Dictionary check: {summary}")
        return {'fixes': fixes, 'errors': errors, 'report': report_path}

    blocking = len(fixes) - sum(1 for f in fixes if f['was'][1] == '' and f['category'] == f['was'][0]) \
        + result['counts'].get('translation in two alphabets', 0)
    logger.info(f"Dictionary check (no autofix): {summary}")
    if blocking:
        if getattr(config, 'dict_force', False):
            logger.warning(f"Dictionary check: {blocking} contradiction(s) with the book, translating as is "
                           f"(--force). Report: {report_path}")
        else:
            raise DictionaryCheckFailed(report_path, blocking)
    return {'fixes': [], 'errors': blocking, 'report': report_path}
