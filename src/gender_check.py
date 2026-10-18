"""
Gender of the characters in a translation.

The weakest spot of a small model: the source says "she", the dictionary says
"Vashti = Вашти, PERSON, she", and the translation still has "Вашти сказал".
Two tools against it, shared by every stage and both pipelines:

- characters_lines(): the characters of the chunk with their gender written
  the way the target language shows it ("Вашти — она (сказала)"), for the
  <characters> block of the prompts. A model copies a verb form it sees far
  more reliably than it maps "she" from the end of a glossary line.
- find_gender_issues(): a check without an LLM. spaCy parses the translation;
  where a dictionary character is the subject, the gender of its predicate
  (a past-tense verb in Slavic languages, a participle with "être"/"essere"/
  "ser", a predicative adjective) must match the dictionary. Only these
  syntactic links are checked: a pronoun two sentences away may refer to
  anything, so pronouns are left to the prompts.

Languages without grammatical gender of the predicate (English, German,
Turkish, Chinese, ...) get no issues; a target language without an installed
spaCy model is not checked (logged once).
"""
import logging
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src import lexicon

logger = logging.getLogger(__name__)

GENDERS = ('he', 'she', 'it', 'they')
# What people write in the gender field of a .dic; the loader normalizes it
# (normalize_gender), `app.py dict clean` (src/dict_clean.py) rewrites the file
GENDER_SYNONYMS = {
    'he': {'он', 'м', 'муж', 'мужской', 'm', 'male', 'masc', 'masculine'},
    'she': {'она', 'ж', 'жен', 'женский', 'f', 'female', 'fem', 'feminine'},
    'it': {'оно', 'ср', 'n', 'neuter'},
    'they': {'они', 'pl', 'plural'},
}
GENDER_MAP = {s: g for g, synonyms in GENDER_SYNONYMS.items() for s in synonyms | {g}}


def normalize_gender(value: str) -> str:
    """he/she/it/they for a known spelling ("female", "она", "ж"); any
    other value stripped and casefolded."""
    value = (value or '').strip().casefold()
    return GENDER_MAP.get(value, value)

# How a target language shows a character's gender: pronoun and, where verbs
# or adjectives inflect for it, one sample form. None: the language has no
# such form (an English label is used). Languages without grammatical gender
# of persons are absent: they get no <characters> labels in the target
# language, see gender_label().
_LABELS = {
    'ru': ('он (сказал)', 'она (сказала)', 'оно (сказало)', 'они (сказали)'),
    'uk': ('він (сказав)', 'вона (сказала)', 'воно (сказало)', 'вони (сказали)'),
    'be': ('ён (сказаў)', 'яна (сказала)', 'яно (сказала)', 'яны (сказалі)'),
    'bg': ('той (казал)', 'тя (казала)', 'то (казало)', 'те (казали)'),
    'sr': ('он (рекао)', 'она (рекла)', 'оно (рекло)', 'они (рекли)'),
    'mk': ('тој', 'таа', 'тоа', 'тие'),
    'pl': ('on (powiedział)', 'ona (powiedziała)', 'ono (powiedziało)', 'oni (powiedzieli)'),
    'cs': ('on (řekl)', 'ona (řekla)', 'ono (řeklo)', 'oni (řekli)'),
    'sk': ('on (povedal)', 'ona (povedala)', 'ono (povedalo)', 'oni (povedali)'),
    'hr': ('on (rekao)', 'ona (rekla)', 'ono (reklo)', 'oni (rekli)'),
    'sl': ('on (rekel)', 'ona (rekla)', 'ono (reklo)', 'oni (rekli)'),
    'lt': ('jis (pavargęs)', 'ji (pavargusi)', None, 'jie'),
    'lv': ('viņš (noguris)', 'viņa (nogurusi)', None, 'viņi'),
    'fr': ('il (il est allé)', 'elle (elle est allée)', None, 'ils'),
    'es': ('él (cansado)', 'ella (cansada)', None, 'ellos'),
    'pt': ('ele (cansado)', 'ela (cansada)', None, 'eles'),
    'it': ('lui (stanco)', 'lei (stanca)', None, 'loro'),
    'ca': ('ell (cansat)', 'ella (cansada)', None, 'ells'),
    'ro': ('el (obosit)', 'ea (obosită)', None, 'ei'),
    'el': ('αυτός (κουρασμένος)', 'αυτή (κουρασμένη)', 'αυτό', 'αυτοί'),
    'de': ('er', 'sie', 'es', 'sie (Plural)'),
    'nl': ('hij', 'zij', 'het', 'zij (meervoud)'),
    'sv': ('han', 'hon', 'den', 'de'),
    'da': ('han', 'hun', 'den', 'de'),
    'nb': ('han', 'hun', 'den', 'de'),
    'is': ('hann', 'hún', 'það', 'þau'),
    'en': ('he', 'she', 'it', 'they'),
    'he': ('הוא (אמר)', 'היא (אמרה)', None, 'הם'),
    'ar': ('هو (قال)', 'هي (قالت)', None, 'هم'),
    'hi': ('वह (गया)', 'वह (गई)', None, 'वे'),
    'zh': ('他', '她', '它', '他们'),
    'ja': ('彼', '彼女', 'それ', '彼ら'),
    'ko': ('그', '그녀', '그것', '그들'),
}
_ENGLISH_LABELS = ('male (he)', 'female (she)', 'neuter (it)', 'plural (they)')

# Languages whose persons have no grammatical gender: the gender changes no
# word of the translation, so it is not worth a prompt line
_GENDERLESS = {'tr', 'az', 'uz', 'kk', 'fi', 'et', 'hu', 'fa', 'hy', 'ka', 'id', 'ms',
               'vi', 'th', 'tl', 'sw', 'eu'}

_FEATURE = {'he': 'Masc', 'she': 'Fem'}
# Only the opposite gender is an error: a neuter predicate next to a name is
# an impersonal sentence the parser misread ("Майклу было двадцать два")
_OPPOSITE = {'he': 'Fem', 'she': 'Masc'}

# Past-tense verbs agree with the subject in gender
_VERB_AGREES = {'ru', 'uk', 'be', 'bg', 'sr', 'mk', 'pl', 'cs', 'sk', 'hr', 'sl', 'lt', 'lv',
                'he', 'ar', 'hi'}
# Predicative adjectives agree with the subject
_ADJ_AGREES = _VERB_AGREES | {'fr', 'es', 'pt', 'it', 'ca', 'ro', 'el'}
# The checked languages spaCy publishes a pipeline with a parser for: the
# small one is downloaded when none is installed
_DOWNLOADABLE = {'ru', 'uk', 'pl', 'hr', 'sl', 'lt', 'mk', 'fr', 'es', 'pt', 'it', 'ca', 'ro', 'el'}
# A participle agrees only with these auxiliaries ("elle est allée", but
# "elle a mangé")
_AGREEING_AUX = {
    'fr': {'être'}, 'it': {'essere'}, 'es': {'ser', 'estar'}, 'pt': {'ser', 'estar', 'ficar'},
    'ca': {'ser', 'estar'}, 'ro': {'fi'}, 'el': {'είμαι'},
}
# Slavic: the small models tag a form's gender wrong ("повреждён" as
# feminine). Without the reflexive ending a masculine past form or short
# adjective ends in a consonant ("сказал", "повреждён", "сказав", "powiedział"),
# a feminine one in -a ("сказала", "рада", "powiedziała").
_SLAVIC_FORM_CHECK = {'ru', 'uk', 'be', 'bg', 'pl', 'cs', 'sk'}
_SLAVIC_CONSONANTS = set('бвгджзйклмнпрстфхцчшщўbcdfghjklłmnprstvwzčďňřšťžźżćń')


def _slavic_form(word: str) -> Optional[str]:
    """'Masc' or 'Fem' by the ending of a past form or short adjective."""
    word = lexicon.normalize(word)
    for reflexive in ('ся', 'сь'):
        if word.endswith(reflexive) and len(word) > 3:
            word = word[:-2]
            break
    if word.endswith(('а', 'a')):
        return 'Fem'
    if word[-1:] in _SLAVIC_CONSONANTS:
        return 'Masc'
    return None


# Romance languages: an adjective or participle shows its gender by the
# ending; a word without it ("melhor", "distante", "romancière" tagged
# masculine) is invariant or mistagged. Slavic forms are always gendered.
_ENDINGS = {
    'fr': (('é', 'i', 'u', 't', 's', 'x', 'r', 'l', 'n', 'f', 'd'),
           ('ée', 'ie', 'ue', 'te', 'se', 'ive', 'ère', 'elle', 'enne', 'onne', 'ette', 'de')),
    'es': (('o',), ('a',)), 'pt': (('o',), ('a',)), 'it': (('o',), ('a',)),
    'ca': (('t', 'o', 'u'), ('a',)), 'ro': (('t', 's', 'u'), ('ă',)),
    'el': (('ος', 'ός', 'ης', 'ής'), ('η', 'ή', 'α', 'ά')),
}
# Quotes or a colon between the name and a predicate: the predicate belongs
# to another speaker or clause ("„Kim jest ta Miss Haddon”, zapytał")
_BARRIERS = set('"«»„“”‚‘’:') | {"''", '``'}
_MAX_DISTANCE = 30  # tokens between the name and its predicate
_NAME_LINKS = {'flat', 'flat:name', 'flat:foreign', 'appos', 'compound', 'fixed'}
_SUBJECT_DEPS = {'nsubj', 'nsubj:pass'}
_WORD_RE = re.compile(r'\w+')
# PARALLEL_STAGES=2 checks two chunks from two threads; one spaCy pipeline
# (possibly on the GPU) parses one text at a time
_NLP_LOCK = threading.Lock()


def _get(entry: Any, key: str) -> str:
    value = entry.get(key, '') if isinstance(entry, dict) else getattr(entry, key, '')
    return (value or '').strip()


def gender_label(gender: str, target_lang: str, genderless_in_english: bool = False) -> Optional[str]:
    """How `target_lang` shows `gender` ("она (сказала)"); None for an
    unknown gender, and for a language without grammatical gender of persons
    unless `genderless_in_english` ("female (she)" then)."""
    gender = normalize_gender(gender)
    code = lexicon.lang_code(target_lang)
    if gender not in GENDERS:
        return None
    if code in _GENDERLESS:
        return _ENGLISH_LABELS[GENDERS.index(gender)] if genderless_in_english else None
    i = GENDERS.index(gender)
    labels = _LABELS.get(code)
    return (labels[i] if labels and labels[i] else None) or _ENGLISH_LABELS[i]


def characters(vocab_entries: Iterable[Any], target_lang: str,
               present_in: Optional[str] = None,
               genderless_in_english: bool = False) -> List[Tuple[str, str]]:
    """
    (name, label) for every dictionary character with a gender, the name in
    the target language. With `present_in`, only the characters whose
    translated or source name occurs in that text (case-insensitive).
    """
    haystack = present_in.lower() if present_in is not None else None
    pairs, seen = [], set()
    for entry in vocab_entries or []:
        label = gender_label(_get(entry, 'gender'), target_lang, genderless_in_english)
        target, source = _get(entry, 'target'), _get(entry, 'source')
        name = target or source
        if not label or not name or name in seen:
            continue
        if haystack is not None and not ((target and target.lower() in haystack)
                                         or (source and source.lower() in haystack)):
            continue
        seen.add(name)
        pairs.append((name, label))
    return pairs


def characters_lines(vocab_entries: Iterable[Any], target_lang: str,
                     present_in: Optional[str] = None,
                     genderless_in_english: bool = False) -> List[str]:
    """characters() as the lines of a <characters> block: "Вашти — она (сказала)"."""
    return [f"{name} — {label}" for name, label in
            characters(vocab_entries, target_lang, present_in, genderless_in_english)]


# --- the check ---------------------------------------------------------------

@dataclass
class GenderIssue:
    name: str              # the character as in the dictionary (target language)
    gender: str            # he / she
    words: List[str]       # the predicate words with the other gender
    start: int             # the sentence in the checked text
    end: int
    meta: Dict[str, Any] = field(default_factory=dict)


@lru_cache(maxsize=None)
def _target_nlp(code: str):
    """An installed spaCy pipeline of `code` with a parser, smallest first;
    without one, <code>_core_news_sm is downloaded (SPACY_AUTO_DOWNLOAD) for a
    language spaCy has it for; None (logged once) when there is none."""
    try:
        import spacy
        from spacy.util import is_package
    except Exception:  # pragma: no cover - spaCy is a dependency
        return None
    for kind in ('news', 'web'):
        for size in ('sm', 'md', 'lg', 'trf'):
            name = f"{code}_core_{kind}_{size}"
            if is_package(name):
                try:
                    nlp = spacy.load(name, exclude=['ner'])
                except Exception as e:
                    logger.warning(f"[gender] spaCy model {name} failed to load: {e}")
                    continue
                if 'parser' in nlp.pipe_names:
                    return nlp
    if code in _DOWNLOADABLE:
        from src import ner  # spaCy and the configuration: imported on first use
        name = f"{code}_core_news_sm"
        if ner.ensure_model(name):
            try:
                return spacy.load(name, exclude=['ner'])
            except Exception as e:
                logger.warning(f"[gender] spaCy model {name} failed to load: {e}")
    logger.info(f"[gender] no spaCy model with a parser for '{code}': gender agreement is not checked "
                f"(python -m spacy download {code}_core_news_sm)")
    return None


def checks_language(target_lang: str) -> bool:
    """Whether find_gender_issues can find anything in this language."""
    code = lexicon.lang_code(target_lang)
    return code in _ADJ_AGREES and _target_nlp(code) is not None


# Where a block of the text ends: a sentence never runs across one. Without
# it the parser read a chapter heading as the subject of the next paragraph
# ("### Диана" + "Кингхаммер пришел" -> "Диана пришел").
_BLOCK_TAG_RE = re.compile(r'(?i)</?(?:p|h[1-6]|title|subtitle|v|stanza|poem|div|li|section|epigraph|'
                           r'blockquote|cite|text-author|br|empty-line)\b[^>]*>')
_MD_BLOCK_RE = re.compile(r'\n[ \t]*\n|^[ \t]*#{1,6}[^\n]*$', re.MULTILINE)


def _blocks(text: str, masked: str) -> List[tuple]:
    """(start, end) of the blocks of `text` (paragraphs, headings, verses):
    split at block tags, Markdown blank lines and heading lines."""
    cuts = {0, len(text)}
    for m in _BLOCK_TAG_RE.finditer(text):
        cuts.update(m.span())
    for m in _MD_BLOCK_RE.finditer(text):
        cuts.update(m.span())
    cuts = sorted(cuts)
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if masked[a:b].strip()]


def _masked(text: str) -> str:
    """`text` with its markup blanked out, offsets kept."""
    chars = list(text)
    for start, end in lexicon.non_text_spans(text):
        if start < end:
            chars[start] = '\n'
            chars[start + 1:end] = ' ' * (end - start - 1)
    return ''.join(chars)


def _name_heads(vocab_entries: Iterable[Any], code: str) -> Dict[str, tuple]:
    """The last word of each gendered name, normalized -> (name, gender, the
    normalized words before it); a word shared by characters of different
    genders is dropped. Matched as written, not by stem: a subject stands in
    the dictionary (nominative) form, and the parser often takes another case
    for one ("Ангела уже не было", "«Да» Клиентки было простым")."""
    heads: Dict[str, tuple] = {}
    clashes = set()
    for entry in vocab_entries or []:
        gender = normalize_gender(_get(entry, 'gender'))
        name = _get(entry, 'target')
        if gender not in _FEATURE or not name:
            continue
        words = _WORD_RE.findall(name)
        if not words:
            continue
        key = lexicon.normalize(words[-1])
        if key in heads and heads[key][1] != gender:
            clashes.add(key)
        heads.setdefault(key, (name, gender, [lexicon.normalize(w) for w in words[:-1]]))
    for key in clashes:
        heads.pop(key, None)
    return heads


def _agrees_here(word, code: str, gender: str) -> bool:
    """Whether the gender of this predicate word must follow the subject
    (`gender`: the character's)."""
    if set(word.morph.get('VerbForm')) & {'Conv', 'Inf'}:
        return False  # a gerund ("летя") or an infinitive has no gender
    if code in _SLAVIC_FORM_CHECK:
        return word.pos_ in ('VERB', 'AUX', 'ADJ') and _slavic_form(word.text) == _OPPOSITE[gender]
    if word.pos_ in ('VERB', 'AUX'):
        if code in _VERB_AGREES:
            return True
        if 'Part' not in word.morph.get('VerbForm'):
            return False
        aux = _AGREEING_AUX.get(code, set())
        if not any(c.dep_.startswith(('aux', 'cop')) and c.lemma_.lower() in aux for c in word.children):
            return False
    elif word.pos_ != 'ADJ' or code not in _ADJ_AGREES:
        return False
    elif code not in _VERB_AGREES and not any(c.dep_ == 'cop' for c in word.children):
        return False  # a Romance adjective without "être": the tagger's misread verb
    endings = _ENDINGS.get(code)
    if endings is None:
        return True
    wrong_endings = endings[0] if gender == 'she' else endings[1]
    return lexicon.normalize(word.text).endswith(wrong_endings)


def _separated(a, b) -> bool:
    """Whether tokens a and b are too far apart or split by quotes or a colon."""
    lo, hi = sorted((a.i, b.i))
    if hi - lo > _MAX_DISTANCE:
        return True
    return any(t.text in _BARRIERS for t in a.doc[lo + 1:hi])


def _other_subject(pred, subj, feature: str) -> bool:
    """Whether the predicate has another word of the predicate's gender that
    can be its real subject ("мизинец Милдред вступил" with the name misparsed
    as the subject): a nominative, or an inanimate accusative, whose form is
    the nominative's ("Вашти охватил страх")."""
    def could_be_subject(c) -> bool:
        case = c.morph.get('Case')
        return 'Nom' in case or ('Acc' in case and 'Inan' in c.morph.get('Animacy'))
    return any(c.i != subj.i and c.pos_ in ('NOUN', 'PROPN', 'PRON')
               and feature in c.morph.get('Gender') and could_be_subject(c)
               for c in pred.children)


def _other_person(tok, before: List[str]) -> bool:
    """Whether the words written before the name differ from the
    dictionary's: "Синьор Канту" is not "Синьора Канту"."""
    if not before or tok.i < len(before):
        return False
    prev = tok.doc[tok.i - len(before):tok.i]
    linked = any(t.head == tok or tok.head == t for t in prev)
    words = [lexicon.normalize(t.text) for t in prev]
    return linked and words != before and words[-1] != before[-1]


def _predicates(head, subj) -> List[Any]:
    """The predicate of a subject and the predicates joined to it by "and"
    that have no subject of their own. A joined predicate with another
    subject between it and the name belongs to that subject, whatever the
    parser attached it to ("Король хотел, чтобы Спраг установила…,
    выступила…", "Ангела не было, и она достигла… и подтянулась")."""
    def another_subject_between(c) -> bool:
        lo, hi = sorted((subj.i, c.i))
        return any(t.dep_ in _SUBJECT_DEPS and t.i != subj.i for t in subj.doc[lo + 1:hi])

    out, todo = [], [head]
    while todo:
        p = todo.pop()
        out.append(p)
        todo += [c for c in p.children if c.dep_ == 'conj' and c.pos_ in ('VERB', 'ADJ', 'AUX')
                 and not any(g.dep_ in _SUBJECT_DEPS for g in c.children)
                 and not another_subject_between(c)]
    return out


def find_gender_issues(text: str, vocab_entries: Iterable[Any], target_lang: str) -> List[GenderIssue]:
    """
    Sentences of `text` where a dictionary character (gender he/she) is the
    subject and a predicate word has the other gender. One issue per
    character and sentence.
    """
    code = lexicon.lang_code(target_lang)
    if not text or code not in _ADJ_AGREES:
        return []
    heads = _name_heads(vocab_entries, code)
    if not heads:
        return []
    nlp = _target_nlp(code)
    if nlp is None:
        return []
    masked = _masked(text)
    spans = _blocks(text, masked)
    with _NLP_LOCK:
        docs = list(nlp.pipe([masked[a:b] for a, b in spans]))
    issues: Dict[tuple, GenderIssue] = {}
    for (base, _), doc in zip(spans, docs):
        _find_in_block(doc, base, heads, code, issues)
    return list(issues.values())


def _find_in_block(doc, base: int, heads: dict, code: str, issues: dict):
    """The issues of one parsed block (offsets shifted by `base`) into `issues`."""
    for tok in doc:
        if tok.text[:1].islower():
            continue  # a name is capitalized; Hebrew, Arabic, Hindi have no case
        hit = heads.get(lexicon.normalize(tok.text))
        if hit is None:
            continue
        name, gender, before = hit
        if _other_person(tok, before):
            continue
        # up from "Рэби" to "Мисс" of "Мисс Рэби", never to another word
        # ("сын Кэтрин" misparsed as an apposition)
        subj = tok
        while (subj.dep_ in _NAME_LINKS and subj.head.i != subj.i
               and lexicon.normalize(subj.head.text) in before):
            subj = subj.head
        if subj.dep_ not in _SUBJECT_DEPS or any(c.dep_ == 'conj' for c in subj.children):
            continue  # not the subject, or one of several ("Вашти и Куно пошли")
        if subj.morph.get('Case') and 'Nom' not in subj.morph.get('Case'):
            continue  # "Майклу было двадцать два"
        if 'Plur' in subj.morph.get('Number'):
            continue
        opposite = _OPPOSITE[gender]
        wrong = []
        for pred in _predicates(subj.head, subj):
            if _other_subject(pred, subj, opposite) or _separated(subj, pred):
                continue
            for word in [pred] + [c for c in pred.children if c.dep_.startswith(('cop', 'aux'))]:
                if (opposite in word.morph.get('Gender') and 'Plur' not in word.morph.get('Number')
                        and _agrees_here(word, code, gender)):
                    wrong.append(word.text)
        if wrong:
            # the sentence without the blanked markup around it ("<p>")
            words = [t for t in tok.sent if not t.is_space]
            start, end = base + words[0].idx, base + words[-1].idx + len(words[-1].text)
            key = (name, start)
            if key not in issues:
                issues[key] = GenderIssue(name, gender, [], start, end)
            issues[key].words += [w for w in wrong if w not in issues[key].words]
