"""
Substitution of glossary terms into the source chunk before the first
translation stage (the model used to skip glossary words otherwise).

Rules, in line with lexicon.resolve_terms:
- Priority: a term of more words wins over the shorter ones it contains
  ("Mad Hatter" over "Hatter"), then the longer one, then the leftmost.
  Occurrences never overlap.
- Markup is not touched: tag names and attributes ("<title>",
  l:href="#spidergun") stay as they are.
- Words are separated by any whitespace (a line break inside "Mad\\nHatter"),
  apostrophes may be typographic ("Queen’s Court"). Terms in unspaced
  scripts (CJK, Thai) are matched without word boundaries.
- Case: a lowercase glossary term ("spidergun") matches in any case and the
  target takes over the capital ("Spidergun" -> "Паукопушка"). A term with
  capitals (a proper name) matches as written or in ALL CAPS, so "Will" is
  not replaced in "will".
"""
import re
from typing import Dict, List, Optional, Tuple

from src import lexicon

_APOSTROPHES = "'’‘ʼ`"
_APOSTROPHE_TABLE = str.maketrans({c: "'" for c in _APOSTROPHES})


def _term_pattern(source: str) -> "re.Pattern[str]":
    unspaced = lexicon.is_unspaced(source)
    words = []
    for word in source.split():
        words.append(''.join(f"[{_APOSTROPHES}]" if ch in _APOSTROPHES else re.escape(ch)
                             for ch in word))
    body = (r'\s*' if unspaced else r'\s+').join(words)
    if not unspaced:
        # lookarounds instead of \b: terms may start or end with a non-word character
        body = rf'(?<!\w){body}(?!\w)'
    return re.compile(body, re.IGNORECASE)


def _canon(text: str) -> str:
    return re.sub(r'\s+', ' ', text).translate(_APOSTROPHE_TABLE)


def _adapt(source: str, found: str, target: str) -> Optional[str]:
    """The replacement for an occurrence `found` of `source`, or None when
    the occurrence is a different word (a name written in lowercase)."""
    if _canon(found) == _canon(source):
        return target
    all_caps = len(found) > 1 and found.isupper()
    if source != source.lower():
        return target.upper() if all_caps else None
    if all_caps:
        return target.upper()
    return target[:1].upper() + target[1:] if found[:1].isupper() else target


def replace_vocab_in_text(
    source_text: str,
    vocab_dict: Dict[str, str],
    source_lang: str = None
) -> str:
    """
    Replace glossary terms in source_text with their translations.

    Called BEFORE Stage 1 (INITIAL) translation so the LLM sees the
    translated terms in context. Stages 2-4 (reflection, improve, final_edit)
    see the ORIGINAL source_text, which lets them verify the result.

    Args:
        source_text: Original text to translate
        vocab_dict: Glossary terms of this chunk, source -> target
        source_lang: Source language (reserved)

    Examples:
        >>> replace_vocab_in_text("Mad Hatter and a hatter", {"Hatter": "Шляпник", "Mad Hatter": "Безумный Шляпник"})
        'Безумный Шляпник and a hatter'
        >>> replace_vocab_in_text("<title>Spidergun</title>", {"spidergun": "паукопушка", "title": "заголовок"})
        '<title>Паукопушка</title>'
    """
    if not vocab_dict or not source_text:
        return source_text

    # taken[i] != 0: character i is markup or already replaced
    taken = bytearray(len(source_text))
    for tag in lexicon.MARKUP_TAG_RE.finditer(source_text):
        taken[tag.start():tag.end()] = b'\x01' * (tag.end() - tag.start())

    # (words, length, start, end, replacement)
    candidates: List[Tuple[int, int, int, int, str]] = []
    for source, target in vocab_dict.items():
        if not source or not source.strip() or not target:
            continue
        source = source.strip()
        words, length = len(source.split()), len(source)
        for match in _term_pattern(source).finditer(source_text):
            if any(taken[match.start():match.end()]):
                continue
            replacement = _adapt(source, match.group(0), target)
            if replacement is not None:
                candidates.append((words, length, match.start(), match.end(), replacement))

    accepted = []
    for words, length, start, end, replacement in sorted(candidates, key=lambda c: (-c[0], -c[1], c[2])):
        if not any(taken[start:end]):
            taken[start:end] = b'\x01' * (end - start)
            accepted.append((start, end, replacement))

    out, pos = [], 0
    for start, end, replacement in sorted(accepted):
        out.append(source_text[pos:start])
        out.append(replacement)
        pos = end
    out.append(source_text[pos:])
    return ''.join(out)
