"""
Words of a translation written in two alphabets: "dошло", "Gород", "taкого"
in Russian — the model switched to the other alphabet in the middle of a
word. No LLM stage notices it (the model reads "gолосом" as "голосом").

The words are found and logged, not fixed: the cause is upstream, in the
prompt or the model, and `app.py eval` (src/prompt_eval.py) looks for it (--prompts,
--no-glossary, --no-substitution). A reflection fix whose replacement has
such a word, or a whole word of the other alphabet (find_foreign_words), is
dropped before IMPROVE. Checked:

- Cyrillic targets (ru, uk, be, bg, sr, mk, kk) and Greek: Latin letters
  inside a word of the target alphabet;
- Latin-script targets: Cyrillic letters inside a Latin word (a translation
  from Russian). Greek letters there are notation ("5 μm", "Δx") and stay.

An all-Latin word in a Russian text (a name, an acronym) is not mixed;
markup, URLs and placeholders (lexicon.non_text_spans) and the words of the
dictionary translations are skipped. Other scripts (CJK, Arabic, ...) are not
checked.
"""
import re
import unicodedata
from typing import Iterable, List, Optional, Set

from src import lexicon

CYRILLIC_LANGS = frozenset({'ru', 'uk', 'be', 'bg', 'sr', 'mk', 'kk'})

# Target script -> the alphabet whose letters inside its words are a slip
_FOREIGN = {'CYRILLIC': 'LATIN', 'GREEK': 'LATIN', 'LATIN': 'CYRILLIC'}

_WORD_RE = re.compile(r'[^\W\d_]+')


def _script(ch: str) -> str:
    name = unicodedata.name(ch, '')
    for script in ('LATIN', 'CYRILLIC', 'GREEK'):
        if name.startswith(script):
            return script
    return ''


_SUBTAG_SCRIPTS = {'latn': 'LATIN', 'cyrl': 'CYRILLIC', 'grek': 'GREEK'}


def _script_subtag(lang: str) -> Optional[str]:
    """'LATIN'/'CYRILLIC'/'GREEK' when the language tag names the script
    explicitly (a BCP-47 subtag: 'sr-Latn', 'az-Cyrl'), else None."""
    parts = (lang or '').strip().lower().replace('_', '-').split('-')
    for part in reversed(parts):
        if part in _SUBTAG_SCRIPTS:
            return _SUBTAG_SCRIPTS[part]
    return None


def target_script(target_lang: str) -> Optional[str]:
    """'CYRILLIC', 'GREEK' or 'LATIN' for a target language whose words
    are checked; None for the others. The script comes from target_lang:
    its language code (ru, en, ...), an explicit BCP-47 script subtag
    ('sr-Latn') or the language list of lexicon; never from a fixed pair.
    A region part ('pt-BR', 'zh-CN') does not hide the language."""
    code = lexicon.lang_code(target_lang)
    explicit = _script_subtag(target_lang) or _script_subtag(code)
    if explicit:
        return explicit
    # the primary language subtag only: in 'zh-CA' the region 'ca' is not a language
    primary = code.split('-')[0]
    if primary in CYRILLIC_LANGS:
        return 'CYRILLIC'
    if primary == 'el':
        return 'GREEK'
    if lexicon.is_latin_script(primary):
        return 'LATIN'
    return None


def is_mixed(word: str, script: str) -> bool:
    """True when the word mixes letters of `script` with the alphabet that
    is a slip in it (_FOREIGN)."""
    scripts = {_script(ch) for ch in word}
    return script in scripts and _FOREIGN[script] in scripts


def _protected_words(dictionary_targets: Iterable[str]) -> Set[str]:
    return {lexicon.normalize(w) for t in dictionary_targets for w in _WORD_RE.findall(t or '')}


def find_foreign_words(text: str, target_lang: str, dictionary_targets: Iterable[str] = ()) -> List[str]:
    """The words of `text` written wholly in the alphabet that is a slip in
    the target one (_FOREIGN: "black-ops" in Russian), in order; markup and
    the words of dictionary translations ("SpaceX") skipped."""
    script = target_script(target_lang)
    if not script or not text:
        return []
    foreign = _FOREIGN[script]
    protected = _protected_words(dictionary_targets)
    return [m.group() for start, end in lexicon.text_spans(text)
            for m in _WORD_RE.finditer(text, start, end)
            if {_script(ch) for ch in m.group()} == {foreign}
            and lexicon.normalize(m.group()) not in protected]


def find_mixed_words(text: str, target_lang: str, dictionary_targets: Iterable[str] = ()) -> List[str]:
    """The mixed-alphabet words of `text`, in order; markup and the words of
    dictionary translations ("eBook-ридер") skipped."""
    script = target_script(target_lang)
    if not script or not text:
        return []
    protected = _protected_words(dictionary_targets)
    return [m.group() for start, end in lexicon.text_spans(text)
            for m in _WORD_RE.finditer(text, start, end)
            if is_mixed(m.group(), script) and lexicon.normalize(m.group()) not in protected]


# --- transliterations are reported, not blocked -------------------------------
#
# A stage may leave whole words of the other alphabet in the translation
# ("dazhe", "desyatki", "tela" in a Russian one; Cyrillic words in a Latin
# target). Which alphabet is "the other" comes from target_lang alone
# (target_script: ru -> Cyrillic, en -> Latin; variants like 'pt-BR' or
# 'sr-Latn' included), never from a fixed pair. Some foreign words stay on
# purpose: the words of the dictionary translations are skipped by
# find_foreign_words itself; the rest is BASIC_FOREIGN_WORDS plus all-caps
# abbreviations of up to MAX_ABBREV_LEN letters ("NASA").

# Not "a": a lone Latin "a" in a Russian text is the usual slip for the
# conjunction "а", not a foreign word.
BASIC_FOREIGN_WORDS = frozenset({
    'magnum', 'opus',      # "magnum opus"
})

MIN_ABBREV_LEN = 2   # a lone capital ("A") is a slip, not an abbreviation
MAX_ABBREV_LEN = 5


def is_whitelisted_foreign_word(word: str) -> bool:
    """A whole word of the other alphabet the translation keeps on purpose:
    a word of BASIC_FOREIGN_WORDS or an all-caps abbreviation of up to
    MAX_ABBREV_LEN letters ("NASA"; at least MIN_ABBREV_LEN). The basic list
    is applied in either direction - a Cyrillic word never equals a Latin entry."""
    if not word:
        return False
    if word.lower() in BASIC_FOREIGN_WORDS:
        return True
    return MIN_ABBREV_LEN <= len(word) <= MAX_ABBREV_LEN and word.upper() == word


def find_unexpected_foreign_words(text: str, target_lang: str,
                                  dictionary_targets: Iterable[str] = ()) -> List[str]:
    """find_foreign_words minus what the translation keeps on purpose: the
    transliterations a stage invents ("dazhe", "desyatki" - in the target's
    slip alphabet, whatever target_script says it is) stay, "magnum opus",
    and all-caps abbreviations ("NASA") do not. The caller logs and
    counts, it never blocks."""
    return [w for w in find_foreign_words(text, target_lang, dictionary_targets)
            if not is_whitelisted_foreign_word(w)]
