"""
Language-aware lexical helpers shared by every dictionary code path.

- get_stop_words(lang): stop words for the source language (NLTK + spaCy).
- find_terms(text, terms, lang): which glossary terms occur in a text chunk,
  including inflected forms (spidergun -> spiderguns, паукопушка ->
  паукопушками).

No regular expressions on purpose: \\b and \\w-based patterns assume
space-separated words and silently fail on CJK, where a term is a run of
characters inside an unbroken sentence. Words are split by Unicode
category instead, and terms written in a script without spaces between
words are matched as substrings.

Inflected forms are matched by comparing normalized keys of each word:
casefolded surface form, NLTK Snowball stem (when the language has one)
and, when the caller passes a lemma map built by spaCy, the lemma. A
Snowball stem can merge a few unrelated words ("universe"/"university"),
which only puts an extra glossary line into the prompt.
"""
from functools import lru_cache
import importlib
import logging
import unicodedata
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

# Language name (as in SOURCE_LANG) -> ISO 639-1 code. Codes map to themselves.
_LANG_CODES = {
    'russian': 'ru', 'english': 'en', 'french': 'fr', 'german': 'de',
    'spanish': 'es', 'italian': 'it', 'chinese': 'zh', 'japanese': 'ja',
    'dutch': 'nl', 'portuguese': 'pt', 'polish': 'pl', 'ukrainian': 'uk',
    'catalan': 'ca', 'danish': 'da', 'finnish': 'fi', 'swedish': 'sv',
    'norwegian': 'nb', 'korean': 'ko', 'romanian': 'ro', 'greek': 'el',
    'lithuanian': 'lt', 'macedonian': 'mk', 'croatian': 'hr', 'slovenian': 'sl',
    'arabic': 'ar', 'hungarian': 'hu', 'turkish': 'tr', 'indonesian': 'id',
    'hebrew': 'he', 'czech': 'cs', 'no': 'nb',
}

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
    return _LANG_CODES.get(lang, lang)


@lru_cache(maxsize=None)
def get_stop_words(lang: str) -> FrozenSet[str]:
    """Stop words for `lang`: NLTK list ∪ spaCy list ∪ markup words
    (∪ fiction-specific extras for English).

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
                words.update(w.casefold() for w in stopwords.words(nltk_name))
        except Exception as e:  # ImportError, offline download, broken corpus
            logger.debug(f"NLTK stop words unavailable for {code}: {e}")

    try:
        module = importlib.import_module(f"spacy.lang.{code}.stop_words")
        words.update(w.casefold() for w in module.STOP_WORDS)
    except Exception as e:
        logger.debug(f"spaCy stop words unavailable for {code}: {e}")

    if code == 'en':
        words.update(_ENGLISH_BOOK_STOP_WORDS)
    return frozenset(words)


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


def tokenize(text: str) -> List[str]:
    """Split normalized text into words: maximal runs of letters, marks and
    digits. Apostrophes, hyphens and punctuation separate words, so
    "spider-gun's" -> ["spider", "gun", "s"]. A switch between an unspaced
    script and any other one also ends a word, so a Latin name inside
    Japanese text stays a word of its own ("ABC社の製品" -> ["abc", "社の製品"])."""
    tokens, current, current_unspaced = [], [], False
    for ch in normalize(text):
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


def _keys(word: str, code: str, lemma_map: Optional[Dict[str, Set[str]]]) -> Set[str]:
    keys = {word, _stem(code, word)}
    if lemma_map:
        for lemma in lemma_map.get(word, ()):
            keys.add(lemma)
            keys.add(_stem(code, lemma))
    return keys


def find_terms(text: str, terms: Iterable[str], lang: str,
               lemma_map: Optional[Dict[str, Set[str]]] = None) -> List[str]:
    """Return the terms (as given) that occur in `text`.

    A multi-word term matches a run of consecutive words. Each word matches
    when the two share a key: the surface form, its Snowball stem or a lemma
    from `lemma_map` ({normalized surface form: {normalized lemma, ...}},
    usually built from the spaCy doc of the chunk). Terms in unspaced
    scripts are matched as substrings of the normalized text.
    """
    code = lang_code(lang)
    terms = [t for t in dict.fromkeys(terms) if t and t.strip()]
    if not text or not terms:
        return []

    normalized_text = None
    text_keys = None
    index: Dict[str, Set[int]] = {}
    matched = []

    for term in terms:
        if is_unspaced(term):
            if normalized_text is None:
                normalized_text = normalize(text)
            if normalize(term).strip() in normalized_text:
                matched.append(term)
            continue

        term_words = tokenize(term)
        if not term_words:
            continue
        if text_keys is None:
            text_keys = [_keys(w, code, lemma_map) for w in tokenize(text)]
            for pos, keys in enumerate(text_keys):
                for key in keys:
                    index.setdefault(key, set()).add(pos)

        term_keys = [_keys(w, code, lemma_map) for w in term_words]
        starts = set()
        for key in term_keys[0]:
            starts |= index.get(key, set())
        n = len(term_keys)
        for start in starts:
            if start + n <= len(text_keys) and all(
                    term_keys[j] & text_keys[start + j] for j in range(1, n)):
                matched.append(term)
                break
    return matched
