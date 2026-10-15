"""
Words of a translation written in two alphabets: "dети", "gолосом",
"taкого" in Russian. A small model starts the word with the Latin token of
the same sound or shape and goes on in the target alphabet; no LLM stage
notices it, since the model reads "gолосом" as "голосом".

fix_mixed_script() puts such a word back into the alphabet of the target
language without an LLM:

- a word is touched only when it has letters of both the target alphabet and
  a foreign one; an all-Latin word in a Russian text (a name, an acronym) is
  left alone, and so are markup, URLs and placeholders (lexicon.non_text_spans);
- each foreign letter has candidates by shape and by sound, most likely
  first ("c" -> "с", "ц"); the candidates are limited to the alphabet of the
  language ("g" -> "ґ" only in Ukrainian);
- the word is replaced only when a variant is a real word: known to
  pymorphy3 (Russian; Ukrainian with pymorphy3-dicts-uk), standing elsewhere
  in the same text, or sharing its stem with a dictionary translation
  ("Вортy" -> "Ворту" for "Ворта"). Without a word list for the language a
  variant that is the only one possible also goes (at most two foreign
  letters), and so do look-alike letters ("Вiн" -> "Він"): they change
  nothing a reader sees;
- whatever stays ambiguous is reported, not guessed: the caller logs it.

Targets in a Cyrillic or the Greek alphabet get the Latin letters fixed; a
Latin-script target gets Cyrillic letters fixed (a translation from
Russian). Greek letters in a Latin-script text are left alone: they are
notation ("5 μm", "Δx", "λmax"), not a slip of the model. Other scripts (CJK,
Arabic, ...) are not checked.
"""
import logging
import re
import unicodedata
from functools import lru_cache
from itertools import islice, product
from typing import Callable, Iterable, List, Optional, Set, Tuple

from src import lexicon

logger = logging.getLogger(__name__)

CYRILLIC_ALPHABETS = {
    'ru': 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
    'uk': 'абвгґдеєжзиіїйклмнопрстуфхцчшщьюя',
    'be': 'абвгдеёжзійклмнопрстуўфхцчшыьэюя',
    'bg': 'абвгдежзийклмнопрстуфхцчшщъьюя',
    'sr': 'абвгдђежзијклљмнњопрстћуфхцчџш',
    'mk': 'абвгдѓежзѕијклљмнњопрстќуфхцчџш',
    'kk': 'аәбвгғдеёжзийкқлмнңоөпрстуұүфхһцчшщъыіьэюя',
}
_GREEK_ALPHABET = 'αβγδεζηθικλμνξοπρστυφχψωάέήίόύώϊϋΐΰς'

# Foreign letter -> candidates in the target alphabet, the most likely first:
# the letter of the same shape, then of the same sound. An uppercase letter
# not listed takes the uppercase of the lowercase candidates.
_LATIN_TO_CYRILLIC = {
    'a': 'а', 'b': 'бьв', 'c': 'сц', 'd': 'д', 'e': 'еэє', 'f': 'ф', 'g': 'гґ',
    'h': 'хнгһ', 'i': 'іиїй', 'j': 'йј', 'k': 'кқ', 'l': 'л', 'm': 'м', 'n': 'нпң',
    'o': 'оө', 'p': 'рп', 'q': 'к', 'r': 'рг', 's': 'сѕ', 't': 'т', 'u': 'уиүұ',
    'v': 'вў', 'w': 'шв', 'x': 'х', 'y': 'уыйў', 'z': 'з',
    'B': 'ВБ', 'H': 'НХГҺ', 'N': 'НП', 'P': 'РП', 'R': 'РГ', 'Y': 'УЫЙЎ',
}
_LATIN_TO_GREEK = {
    'a': 'α', 'b': 'β', 'd': 'δ', 'e': 'εη', 'f': 'φ', 'g': 'γ', 'h': 'η', 'i': 'ι',
    'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'νη', 'o': 'οω', 'p': 'ρπ', 'r': 'ρ', 's': 'σς',
    't': 'τ', 'u': 'υ', 'v': 'νβ', 'w': 'ω', 'x': 'χξ', 'y': 'υγ', 'z': 'ζ',
    'B': 'Β', 'E': 'ΕΗ', 'H': 'ΗΧ', 'N': 'ΝΗ', 'P': 'ΡΠ', 'X': 'ΧΞ', 'Y': 'ΥΓ',
}
_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'vbw', 'г': 'gh', 'ґ': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'є': 'e', 'ж': 'zj', 'з': 'z', 'и': 'iu', 'і': 'i', 'ї': 'i', 'й': 'jiy', 'ј': 'j',
    'к': 'kc', 'л': 'l', 'м': 'm', 'н': 'nh', 'о': 'o', 'п': 'pn', 'р': 'pr', 'с': 'cs',
    'ѕ': 's', 'т': 't', 'у': 'uy', 'ў': 'u', 'ф': 'f', 'х': 'xh', 'ц': 'c', 'ч': 'c',
    'ш': 'sw', 'щ': 's', 'ы': 'y', 'ь': 'b', 'э': 'e', 'ю': 'u', 'я': 'a',
    'В': 'BVW', 'Н': 'HN', 'Р': 'PR', 'С': 'CS', 'У': 'YU', 'Х': 'XH', 'К': 'KC',
}
# Target script -> (the foreign script fixed in its words, candidate table)
_FOREIGN = {
    'CYRILLIC': ('LATIN', _LATIN_TO_CYRILLIC),
    'GREEK': ('LATIN', _LATIN_TO_GREEK),
    'LATIN': ('CYRILLIC', _CYRILLIC_TO_LATIN),
}

# Letters that look exactly alike: replacing one changes nothing a reader
# sees, so a word without a word list may get them without a check
_HOMOGLYPHS = set(zip(
    'aceijopsxyABCEHIJKMOPSTXY' 'ABEZHIKMNOPTXYov',
    'асеіјорѕхуАВСЕНІЈКМОРЅТХУ' 'ΑΒΕΖΗΙΚΜΝΟΡΤΧΥον'))
_HOMOGLYPHS |= {(b, a) for a, b in _HOMOGLYPHS}

_WORD_RE = re.compile(r'[^\W\d_]+')
_MAX_VARIANTS = 512           # a word with more foreign letters is reported, not fixed
_MAX_UNVALIDATED_FOREIGN = 2  # an only variant without a word list: at most this many letters


def _script(ch: str) -> str:
    name = unicodedata.name(ch, '')
    for script in ('LATIN', 'CYRILLIC', 'GREEK'):
        if name.startswith(script):
            return script
    return ''


def target_script(target_lang: str) -> Optional[str]:
    """'CYRILLIC', 'GREEK' or 'LATIN' for a target language whose words
    are checked; None for the others."""
    code = lexicon.lang_code(target_lang)
    if code in CYRILLIC_ALPHABETS:
        return 'CYRILLIC'
    if code == 'el':
        return 'GREEK'
    if lexicon.is_latin_script(code):
        return 'LATIN'
    return None


def _candidates(ch: str, table: dict, alphabet: Optional[str]) -> str:
    found = table.get(ch)
    if found is None and ch.isupper():
        found = table.get(ch.lower(), '').upper()
    found = found or ''
    if alphabet is not None:
        found = ''.join(c for c in found if c.lower() in alphabet)
    return found


@lru_cache(maxsize=None)
def _morph(code: str):
    """pymorphy3 analyzer for ru/uk, None when it or its dictionary is missing."""
    if code not in ('ru', 'uk'):
        return None
    try:
        import pymorphy3
        return pymorphy3.MorphAnalyzer(lang=code)
    except Exception as e:
        logger.warning(f"pymorphy3 for '{code}' unavailable ({e}): mixed-alphabet words are fixed "
                       f"without a word list (pip install -e .)")
        return None


def is_mixed(word: str, script: str) -> bool:
    """True when the word mixes letters of `script` with the alphabet fixed
    for it (_FOREIGN)."""
    scripts = {_script(ch) for ch in word}
    return script in scripts and _FOREIGN[script][0] in scripts


def _protected_words(dictionary_targets: Iterable[str]) -> Set[str]:
    return {lexicon.normalize(w) for t in dictionary_targets for w in _WORD_RE.findall(t or '')}


def _mixed_spans(text: str, script: str, protected: Set[str]) -> List[Tuple[int, int]]:
    """(start, end) of the mixed words outside markup and dictionary words."""
    return [m.span() for start, end in lexicon.text_spans(text)
            for m in _WORD_RE.finditer(text, start, end)
            if is_mixed(m.group(), script) and lexicon.normalize(m.group()) not in protected]


def find_mixed_words(text: str, target_lang: str, dictionary_targets: Iterable[str] = ()) -> List[str]:
    """The mixed-alphabet words of `text`, in order: markup and the words of
    dictionary translations skipped, as in fix_mixed_script."""
    script = target_script(target_lang)
    if not script or not text:
        return []
    return [text[a:b] for a, b in _mixed_spans(text, script, _protected_words(dictionary_targets))]


def _attested_words(text: str, script: str) -> Set[str]:
    return {lexicon.normalize(seg) for seg in _WORD_RE.findall(' '.join(lexicon.text_segments(text)))
            if all(_script(ch) == script for ch in seg)}


def _fix_word(word: str, script: str, alphabet: Optional[str], known: Callable[[str], bool],
              has_word_list: bool) -> Optional[str]:
    foreign, table = _FOREIGN[script]
    foreign_positions = [i for i, ch in enumerate(word) if _script(ch) == foreign]
    options = []
    for i in foreign_positions:
        cands = _candidates(word[i], table, alphabet)
        if not cands:
            return None
        options.append(cands)
    variants = []
    for combo in islice(product(*options), _MAX_VARIANTS + 1):
        chars = list(word)
        for i, ch in zip(foreign_positions, combo):
            chars[i] = ch
        variants.append(''.join(chars))
    if len(variants) > _MAX_VARIANTS:
        return None
    for variant in variants:  # most likely letters first
        if known(variant):
            return variant
    if has_word_list:
        return None
    if len(variants) == 1 and len(foreign_positions) <= _MAX_UNVALIDATED_FOREIGN:
        return variants[0]
    # no word list: look-alike letters only, when every foreign letter has one
    lookalike = list(word)
    for i, cands in zip(foreign_positions, options):
        same = [c for c in cands if (word[i], c) in _HOMOGLYPHS]
        if not same:
            return None
        lookalike[i] = same[0]
    return ''.join(lookalike)


def fix_mixed_script(text: str, target_lang: str,
                     dictionary_targets: Iterable[str] = ()) -> Tuple[str, List[Tuple[str, str]], List[str]]:
    """
    Put the mixed-alphabet words of a translation back into the target
    alphabet (see the module docstring).

    dictionary_targets: translations from the .dic of this chunk; a word of
    one of them is never touched ("eBook-ридер" stays), and a variant sharing
    a stem with one of their words counts as a real word.

    Returns (text, fixes, unfixed): fixes are (old, new) word pairs, unfixed
    the mixed words left as they are.
    """
    script = target_script(target_lang)
    if not script or not text:
        return text, [], []
    code = lexicon.lang_code(target_lang)
    protected = _protected_words(dictionary_targets)
    spans = _mixed_spans(text, script, protected)
    if not spans:
        return text, [], []

    alphabet = CYRILLIC_ALPHABETS.get(code) if script == 'CYRILLIC' else (
        _GREEK_ALPHABET if script == 'GREEK' else None)
    dictionary_stems = {lexicon.stem(w, code) for w in protected}
    attested = _attested_words(text, script)
    morph = _morph(code)

    def known(variant: str) -> bool:
        norm = lexicon.normalize(variant)
        if norm in attested or (variant[:1].isupper() and lexicon.stem(norm, code) in dictionary_stems):
            return True
        return bool(morph and morph.word_is_known(norm))

    fixes, unfixed, out, pos = [], [], [], 0
    for start, end in spans:
        word = text[start:end]
        new = _fix_word(word, script, alphabet, known, morph is not None)
        if new is None:
            unfixed.append(word)
            continue
        out.append(text[pos:start])
        out.append(new)
        pos = end
        fixes.append((word, new))
    out.append(text[pos:])
    return ''.join(out), fixes, unfixed

