"""
Language-aware lexical helpers shared by every dictionary code path.

- get_stop_words(lang): stop words for the source language (NLTK + spaCy).
- resolve_terms / find_terms(text, terms, lang): which glossary terms occur
  in a text chunk, including inflected forms (spidergun -> spiderguns,
  паукопушка -> паукопушками).
- non_text_spans / text_segments: markup that is not text of the book.
- term_rank: priority of overlapping terms.

No regular expressions for word matching on purpose: \\b and \\w-based
patterns assume space-separated words and silently fail on CJK, where a term
is a run of characters inside an unbroken sentence. Words are split by
Unicode category instead, and terms written in a script without spaces
between words are matched as substrings.

Inflected forms are matched by comparing normalized keys of each word:
casefolded surface form, NLTK Snowball stem (when the language has one)
and, when the caller passes a lemma map built by spaCy, the lemma. Stems
and lemmas that are stop words are ignored, so "Ares" does not match "are".
A Snowball stem can still merge a few unrelated words ("universe"/
"university"), which only puts an extra glossary line into the prompt.

Overlapping terms are resolved by priority (term_rank): a term made of more
words wins over the shorter ones it contains ("Mad Hatter" over "Hatter"),
then the longer one, then the leftmost. A term whose every occurrence is
covered by a winner is "shadowed" and not reported as found, so the prompt
never lists "Hatter = Шляпник" next to "Mad Hatter = Безумный Шляпник" for
a chunk that only has the latter. term_substitution.py replaces terms with
the same priority, and both obey the same limits:
- markup (non_text_spans) is not text and breaks a multi-word term, so
  "Mad</p><p>Hatter" is two words of two paragraphs, not the phrase;
- only an occurrence in the term's case (or ALL CAPS) can shadow another
  term: "the mad Hatter" is not "Mad Hatter", so "Hatter" stays found.
"""
from functools import lru_cache
import importlib
import logging
import re
import unicodedata
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from src.config import LANG_CODE_MAP
from src.fb2_structure import markup_tags

logger = logging.getLogger(__name__)

# Markdown that is not text (Calibre-pipeline chunks): link and image targets
# ](url "title") and ](<url>), reference definitions "[id]: url", attribute
# blocks {#id .class} / {width="50%"}, autolinks <https://...>, bare URLs.
_MARKDOWN_NON_TEXT_RE = re.compile(
    r'\]\(<[^<>\n]*>(?:\s+"[^"\n]*")?\)'
    r'|\]\([^()\s]*(?:\([^()\s]*\)[^()\s]*)*(?:\s+"[^"\n]*")?\)'
    r'|^ {0,3}\[[^\]\n]+\]:[^\n]*'
    r'|\{[#.][^{}\n]*\}|\{[A-Za-z][\w-]*="[^"\n]*"[^{}\n]*\}'
    r'|<(?:https?|ftp|mailto):[^<>\s]*>'
    r'|(?:https?|ftp)://[^\s<>()\[\]]+',
    re.MULTILINE)


def non_text_spans(text: str) -> List[Tuple[int, int]]:
    """Sorted (start, end) spans of `text` that are markup, not text of the
    book: FB2/HTML tags (fb2_structure.markup_tags, so "a<b and c>d" and a
    pandoc-escaped "\\<Skill acquired\\>" stay text) and the markdown above."""
    spans = [m.span() for m in markup_tags(text)]
    spans += [m.span() for m in _MARKDOWN_NON_TEXT_RE.finditer(text)]
    return sorted(spans)


def text_segments(text: str) -> List[str]:
    """The pieces of `text` between its non_text_spans."""
    pieces, pos = [], 0
    for start, end in non_text_spans(text):
        if start >= pos:
            pieces.append(text[pos:start])
        pos = max(pos, end)
    pieces.append(text[pos:])
    return pieces


# ISO code -> NLTK stopwords corpus file. NLTK has no list for ja, ko, pl,
# uk, lt, mk, hr, cs — spaCy covers those.
_NLTK_STOPWORDS = {
    'ar': 'arabic', 'az': 'azerbaijani', 'eu': 'basque', 'be': 'belarusian',
    'bn': 'bengali', 'ca': 'catalan', 'zh': 'chinese', 'da': 'danish',
    'nl': 'dutch', 'en': 'english', 'fi': 'finnish', 'fr': 'french',
    'de': 'german', 'el': 'greek', 'he': 'hebrew', 'hu': 'hungarian',
    'id': 'indonesian', 'it': 'italian', 'kk': 'kazakh', 'ne': 'nepali',
    'nb': 'norwegian', 'pt': 'portuguese', 'ro': 'romanian', 'ru': 'russian',
    'sl': 'slovene', 'es': 'spanish', 'sv': 'swedish', 'tg': 'tajik',
    'ta': 'tamil', 'tr': 'turkish',
}

# ISO code -> NLTK Snowball stemmer (algorithmic, needs no corpus download).
_SNOWBALL = {
    'ar': 'arabic', 'da': 'danish', 'nl': 'dutch', 'en': 'english',
    'fi': 'finnish', 'fr': 'french', 'de': 'german', 'hu': 'hungarian',
    'it': 'italian', 'nb': 'norwegian', 'pt': 'portuguese', 'ro': 'romanian',
    'ru': 'russian', 'es': 'spanish', 'sv': 'swedish',
}

# Markup words that leak into the text of FB2/HTML books in any language.
_MARKUP_STOP_WORDS = {"p", "section", "emphasis", "strong", "subtitle", "epigraph", "stanza"}

# Frequent words of English fiction that are not glossary material but are
# missing from the general-purpose NLTK/spaCy lists.
_ENGLISH_BOOK_STOP_WORDS = {
    "said", "would", "could", "upon", "must", "might", "shall", "may", "yet",
    "thing", "things", "way", "ways", "like", "even", "also", "back", "still",
    "much", "get", "got", "go", "went", "come", "came", "see", "saw", "know",
    "knew", "think", "thought", "want", "wanted", "take", "took", "give", "gave",
    "make", "made", "first", "second", "one", "two", "time", "times", "new",
    "old", "great", "little", "chapter", "part", "book", "volume", "page",
    "title", "author", "name", "ask", "asked", "say", "tell", "told", "look",
    "looked", "seem", "seemed", "feel", "felt", "leave", "left", "call",
    "called", "turn", "turned", "inside", "every", "another", "however",
    "though", "although", "therefore", "since", "without", "within", "around",
    "toward", "towards", "ever", "never", "always", "often", "sometimes",
    "usually", "already", "perhaps", "maybe", "certainly", "exactly",
    "especially",
}

# Unicode name prefixes of scripts that do not put spaces between words
# (or, for Hangul, glue particles onto the word): a term in these scripts
# is matched as a substring.
_UNSPACED_SCRIPTS = (
    "CJK ", "IDEOGRAPHIC", "HIRAGANA", "KATAKANA", "HALFWIDTH KATAKANA",
    "HANGUL", "HALFWIDTH HANGUL", "THAI", "LAO", "KHMER", "MYANMAR", "TIBETAN",
)


def lang_code(lang: str) -> str:
    """'english'/'English'/'en' -> 'en'."""
    lang = (lang or '').strip().lower()
    return LANG_CODE_MAP.get(lang, lang)


@lru_cache(maxsize=None)
def get_stop_words(lang: str) -> FrozenSet[str]:
    """Stop words for `lang`: NLTK list ∪ spaCy list ∪ markup words
    (∪ fiction-specific extras for English), normalized with normalize().
    Look words up with is_stop_word() (or normalize() them first): a plain
    .lower() misses casefold-only forms such as German "daß" -> "dass".

    Either source may be missing (NLTK corpus not downloadable offline,
    language unknown to one of the libraries) — the other one still applies.
    """
    code = lang_code(lang)
    words: Set[str] = set(_MARKUP_STOP_WORDS)

    nltk_name = _NLTK_STOPWORDS.get(code)
    if nltk_name:
        try:
            import nltk
            from nltk.corpus import stopwords
            try:
                nltk.data.find('corpora/stopwords')
            except LookupError:
                nltk.download('stopwords', quiet=True)
            if nltk_name in stopwords.fileids():
                words.update(normalize(w) for w in stopwords.words(nltk_name))
        except Exception as e:  # ImportError, offline download, broken corpus
            logger.debug(f"NLTK stop words unavailable for {code}: {e}")

    try:
        module = importlib.import_module(f"spacy.lang.{code}.stop_words")
        words.update(normalize(w) for w in module.STOP_WORDS)
    except Exception as e:
        logger.debug(f"spaCy stop words unavailable for {code}: {e}")

    if code == 'en':
        words.update(_ENGLISH_BOOK_STOP_WORDS)
    return frozenset(words)


def is_stop_word(word: str, stop_words: Iterable[str]) -> bool:
    """`word` in a set produced by get_stop_words()/normalize_words()."""
    return normalize(word).strip() in stop_words


def normalize_words(words: Iterable[str]) -> FrozenSet[str]:
    """Normalize a caller-supplied stop-word list the same way."""
    return frozenset(normalize(w).strip() for w in words)


@lru_cache(maxsize=None)
def _stemmer(code: str):
    name = _SNOWBALL.get(code)
    if not name:
        return None
    try:
        from nltk.stem.snowball import SnowballStemmer
        return SnowballStemmer(name)
    except Exception as e:
        logger.debug(f"Snowball stemmer unavailable for {code}: {e}")
        return None


@lru_cache(maxsize=200000)
def _stem(code: str, word: str) -> str:
    stemmer = _stemmer(code)
    return stemmer.stem(word) if stemmer else word


def normalize(text: str) -> str:
    """NFKC (full-width Latin -> ASCII, compatibility forms) + casefold."""
    return unicodedata.normalize("NFKC", text).casefold()


def _is_word_char(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LMN"


def _is_unspaced_char(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith(_UNSPACED_SCRIPTS)


def is_unspaced(term: str) -> bool:
    """True when the term contains characters of a script written without
    spaces between words (CJK, Thai, ...)."""
    return any(_is_unspaced_char(ch) for ch in term)


def _split_words(text: str) -> List[str]:
    tokens, current, current_unspaced = [], [], False
    for ch in text:
        if not _is_word_char(ch):
            if current:
                tokens.append(''.join(current))
                current = []
            continue
        unspaced = _is_unspaced_char(ch)
        if current and unspaced != current_unspaced:
            tokens.append(''.join(current))
            current = []
        current.append(ch)
        current_unspaced = unspaced
    if current:
        tokens.append(''.join(current))
    return tokens


def tokenize(text: str) -> List[str]:
    """Split normalized text into words: maximal runs of letters, marks and
    digits. Apostrophes, hyphens and punctuation separate words, so
    "spider-gun's" -> ["spider", "gun", "s"]. A switch between an unspaced
    script and any other one also ends a word, so a Latin name inside
    Japanese text stays a word of its own ("ABC社の製品" -> ["abc", "社の製品"])."""
    return _split_words(normalize(text))


def _surface_words(text: str) -> Optional[List[str]]:
    """The words of tokenize(text) with their case kept; None in the rare
    case casefolding changed the word count."""
    words = _split_words(unicodedata.normalize("NFKC", text))
    return words if len(words) == len(tokenize(text)) else None


def term_rank(term: str) -> Tuple[int, int]:
    """Priority of a glossary term among overlapping ones, higher wins:
    (number of words, length). Shared by matching, substitution and the
    order of glossary lines in the prompt."""
    folded = normalize(term).strip()
    return (1 if is_unspaced(term) else len(tokenize(term)), len(folded))


def _case_shape(word: str) -> str:
    if len(word) > 1 and word.isupper():
        return 'upper'
    return 'title' if word[:1].isupper() else 'lower'


def _case_fits(term: str, term_words: Optional[List[str]], found: List[Optional[str]]) -> bool:
    """Whether an occurrence may shadow other terms: a lowercase term fits
    any case; a term with capitals fits the same capitalisation of every
    word (inflection allowed: "Mad Hatters") or ALL CAPS, like
    term_substitution accepts it."""
    if term == term.lower() or term_words is None or None in found:
        return True
    joined = ' '.join(found)
    if len(joined) > 1 and joined.isupper():
        return True
    return all(_case_shape(t) == _case_shape(w) for t, w in zip(term_words, found))


def _keys(word: str, code: str, lemma_map: Optional[Dict[str, Set[str]]],
          stop_words: FrozenSet[str]) -> Set[str]:
    """Match keys of one word: its surface form, plus stem and lemma forms.

    A stop word, or a stem/lemma that is a stop word, contributes only its
    surface form: otherwise a name ending in -s collapses onto a common word
    (stem("Ares") == "are", "Wells" -> "well") and lands in every chunk.
    """
    keys = {word}
    if word in stop_words:
        return keys
    forms = [word, *(lemma_map.get(word, ()) if lemma_map else ())]
    for form in forms:
        for key in (form, _stem(code, form)):
            if key not in stop_words:
                keys.add(key)
    return keys


def _pick(spans: List[Tuple[str, int, int, Tuple[int, int]]], size: int) -> Set[str]:
    """Greedy non-overlapping selection: higher rank first, then leftmost.
    Returns the terms that kept at least one occurrence."""
    taken = bytearray(size)
    kept: Set[str] = set()
    for term, start, end, _ in sorted(spans, key=lambda s: (-s[3][0], -s[3][1], s[1])):
        if not any(taken[start:end]):
            taken[start:end] = b'\x01' * (end - start)
            kept.add(term)
    return kept


def resolve_terms(text: str, terms: Iterable[str], lang: str,
                  lemma_map: Optional[Dict[str, Set[str]]] = None) -> Tuple[List[str], List[str]]:
    """Return (found, shadowed): the terms (as given) that occur in `text`
    and the ones that occur only inside a higher-priority term.

    A multi-word term matches a run of consecutive words. Each word matches
    when the two share a key: the surface form, its Snowball stem or a lemma
    from `lemma_map` ({normalized surface form: {normalized lemma, ...}},
    usually built from the spaCy doc of the chunk). Terms in unspaced
    scripts are matched as substrings of the normalized text. Markup
    (non_text_spans) never matches and no term spans across it. An
    occurrence in another case than the term's (_case_fits) counts as found
    but does not shadow anything.
    """
    code = lang_code(lang)
    terms = [t for t in dict.fromkeys(terms) if t and t.strip()]
    if not text or not terms:
        return [], []
    segments = text_segments(text)

    stop_words = get_stop_words(code)
    normalized_text = None
    text_keys = None
    text_words: List[Optional[str]] = []
    index: Dict[str, Set[int]] = {}
    spans = {False: [], True: []}  # unspaced? -> [(term, start, end, rank)]
    weak = set()  # terms with an occurrence that cannot shadow

    for term in terms:
        rank = term_rank(term)
        if is_unspaced(term):
            if normalized_text is None:
                # \x00 never occurs in a term: no match across markup
                normalized_text = '\x00'.join(normalize(seg) for seg in segments)
            needle = normalize(term).strip()
            pos = normalized_text.find(needle) if needle else -1
            while pos != -1:
                spans[True].append((term, pos, pos + len(needle), rank))
                pos = normalized_text.find(needle, pos + 1)
            continue

        term_words = tokenize(term)
        if not term_words:
            continue
        if text_keys is None:
            text_keys = []
            for seg in segments:
                if text_keys:
                    # a boundary that matches no word: no term across markup
                    text_keys.append(frozenset())
                    text_words.append(None)
                words = tokenize(seg)
                text_keys += [_keys(w, code, lemma_map, stop_words) for w in words]
                text_words += _surface_words(seg) or [None] * len(words)
            for pos, keys in enumerate(text_keys):
                for key in keys:
                    index.setdefault(key, set()).add(pos)

        term_keys = [_keys(w, code, lemma_map, stop_words) for w in term_words]
        term_surface = _surface_words(term)
        starts = set()
        for key in term_keys[0]:
            starts |= index.get(key, set())
        n = len(term_keys)
        for start in starts:
            if start + n <= len(text_keys) and all(
                    term_keys[j] & text_keys[start + j] for j in range(1, n)):
                if _case_fits(term, term_surface, text_words[start:start + n]):
                    spans[False].append((term, start, start + n, rank))
                else:
                    weak.add(term)

    found_set = set(weak)
    if spans[False]:
        found_set |= _pick(spans[False], len(text_keys))
    if spans[True]:
        found_set |= _pick(spans[True], len(normalized_text))
    occurring = {s[0] for group in spans.values() for s in group}
    found = [t for t in terms if t in found_set]
    shadowed = [t for t in terms if t in occurring and t not in found_set]
    return found, shadowed


def find_terms(text: str, terms: Iterable[str], lang: str,
               lemma_map: Optional[Dict[str, Set[str]]] = None) -> List[str]:
    """Return the terms (as given) that occur in `text` and are not shadowed
    by a higher-priority overlapping term. See resolve_terms."""
    return resolve_terms(text, terms, lang, lemma_map)[0]
