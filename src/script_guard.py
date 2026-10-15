"""
Words of a translation written in two alphabets: "dошло", "Gород", "taкого"
in Russian — the model switched to the other alphabet in the middle of a
word. No LLM stage notices it (the model reads "gолосом" as "голосом").

The words are found and logged, not fixed: the cause is upstream, in the
prompt or the model, and scripts/prompt_eval.py looks for it (--prompts,
--no-glossary, --no-substitution). Checked:

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


def target_script(target_lang: str) -> Optional[str]:
    """'CYRILLIC', 'GREEK' or 'LATIN' for a target language whose words
    are checked; None for the others."""
    code = lexicon.lang_code(target_lang)
    if code in CYRILLIC_LANGS:
        return 'CYRILLIC'
    if code == 'el':
        return 'GREEK'
    if lexicon.is_latin_script(code):
        return 'LATIN'
    return None


def is_mixed(word: str, script: str) -> bool:
    """True when the word mixes letters of `script` with the alphabet that
    is a slip in it (_FOREIGN)."""
    scripts = {_script(ch) for ch in word}
    return script in scripts and _FOREIGN[script] in scripts


def _protected_words(dictionary_targets: Iterable[str]) -> Set[str]:
    return {lexicon.normalize(w) for t in dictionary_targets for w in _WORD_RE.findall(t or '')}


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
