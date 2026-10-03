from collections import Counter
import logging
import re
from typing import Optional
import spacy
import spacy.cli
import torch
import numpy as np

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    cp = None
    CUPY_AVAILABLE = False

from src.config import Config
from src import lexicon

logger = logging.getLogger(__name__)

# Initialize config
config = Config()

# Module-level cache for spaCy models (Problem 3 fix)
_nlp_cache = {}

# NER entity categories we care about for a glossary (people, places,
# organizations). Different spaCy pipelines use different label schemes for
# the same categories: most "core_news"/"core_web" models trained on
# OntoNotes-style corpora (en, ja, zh, ru, ...) use ORG/LOC/GPE/PERSON/...,
# but ko_core_news_lg is trained on the KLUE corpus and uses its own
# 2-letter scheme (PS=person, LC=location, OG=organization, DT=date,
# TI=time, QT=quantity) - none of which overlap with the OntoNotes labels.
# Without this, filtering by an OntoNotes-only category list silently
# drops every entity found in Korean text.
NER_CATEGORIES = ["ORG", "LOC", "GPE", "PERSON", "EVENT", "FAC", "PRODUCT", "PS", "LC", "OG"]

# Normalize scheme-specific labels to their OntoNotes-style equivalent so
# .dic output categories stay consistent regardless of which model produced
# them.
# KLUE labels of ko_core_news_lg and the PER of the multilingual xx_ent_wiki_sm
_LABEL_NORMALIZATION = {"PS": "PERSON", "LC": "LOC", "OG": "ORG", "PER": "PERSON"}


def _normalize_label(label):
    return _LABEL_NORMALIZATION.get(label, label)

def _ner_disabled_pipes(lang=None):
    """spaCy components NER does not need. Korean keeps the lemmatizer:
    entity_text() reads the particle of "철수는" from the lemma "철수+는"."""
    keep_lemmatizer = lexicon.lang_code(lang or config.source_lang) == 'ko'
    return ["parser", "attribute_ruler"] + ([] if keep_lemmatizer else ["lemmatizer"])


def _without_leading_articles(ent) -> str:
    """ent.text without the articles spaCy sometimes takes into the span
    ("a Jain", "the platform AI", "l'Empire", "der Kaiser", 一个吉恩人): the
    .dic term must be the name, or "a Jain" lands next to "Jain" as a second
    entry. Articles per language: lexicon.is_article (the language of the
    doc, SOURCE_LANG as fallback). A capitalized article stays ("The
    Warship", "El Greco" may be the name itself), the last token always does.
    """
    text = ent.text.strip()
    if not hasattr(type(ent), '__iter__'):
        return text
    tokens = list(ent)
    lang = _ent_lang(ent)
    cut = 0
    for token in tokens[:-1]:
        word = token.text
        cased = any(c.isupper() or c.islower() for c in word)
        if not lexicon.is_article(word, lang) or (cased and word != word.lower()):
            break
        cut += 1
    if not cut:
        return text
    return ent.text[tokens[cut].idx - tokens[0].idx:].strip()


# Turkish and Azerbaijani attach case suffixes to a proper name after an
# apostrophe: "Ankara'ya", "İstanbul'da", "Ayşe'nin" are Ankara, İstanbul, Ayşe
_APOSTROPHE_SUFFIX_LANGUAGES = {'tr', 'az'}
# A suffix is lowercase and follows a stem of two letters or more, so
# "O'Brien", "D'Angelo", "N'Diaye" stay whole
_APOSTROPHE_SUFFIX_RE = re.compile(r"(?<=\w\w)['’][^\W\d_A-ZÇĞİÖŞÜ]\w*$")


def _ent_lang(ent) -> str:
    """Language of the entity's doc; SOURCE_LANG for the multilingual
    model ("xx") or a doc without one."""
    lang = getattr(getattr(ent, 'doc', None), 'lang_', '')
    return config.source_lang if lang in ('', 'xx') else lang


def entity_text(ent):
    """Entity text without a leading article (_without_leading_articles),
    without a Turkish/Azerbaijani case suffix after an apostrophe
    ("Ankara'ya" -> "Ankara"; "O'Brien" stays) and
    without the grammatical particle (josa) glued to its last word. Korean
    writes "철수는", "서울에서", "영희가" for 철수, 서울, 영희, and the .dic
    term must be the bare name or it matches one form only. The morphology
    comes from the model: tag "ncn+jxt", lemma "철수+는"; particle tags start
    with "j". Other languages have no such tags and pass unchanged."""
    text = _without_leading_articles(ent)
    if lexicon.lang_code(_ent_lang(ent)) in _APOSTROPHE_SUFFIX_LANGUAGES:
        stem = _APOSTROPHE_SUFFIX_RE.sub('', text)
        if stem:
            return stem
    tags, lemmas = ent[-1].tag_.split('+'), ent[-1].lemma_.split('+')
    if len(tags) < 2 or len(tags) != len(lemmas):
        return text
    particle = ''
    while len(tags) > 1 and tags[-1].startswith('j'):
        tags.pop()
        particle = lemmas.pop() + particle
    if particle and text.endswith(particle) and len(text) > len(particle):
        return text[:-len(particle)]
    return text


def _get_nlp(model_name, max_length=200000):
    """Get or create a cached spaCy model instance."""
    if model_name not in _nlp_cache:
        _nlp_cache[model_name] = load_spacy_model(model_name)
        _nlp_cache[model_name].max_length = max_length
    else:
        # Ensure max_length is at least what's requested
        if _nlp_cache[model_name].max_length < max_length:
            _nlp_cache[model_name].max_length = max_length
    return _nlp_cache[model_name]

def load_spacy_model(model_name):
    """
    Attempts to load a spaCy model. If not found, downloads it and tries again.
    """
    try:
        # Try to use GPU
        spacy.prefer_gpu()
        if config.debug:
            print(f"Loading spaCy model: {model_name}")
        return spacy.load(model_name)
    except OSError:
        if config.debug:
            print(f"Model {model_name} not found. Downloading...")
        spacy.cli.download(model_name)
        if config.debug:
            print(f"Model {model_name} downloaded. Loading...")
        return spacy.load(model_name)

def make_vocab(text, stop_words=None, min_count_ner=5, min_count_word=10, min_word_length=5,
               include_words=None, lang=None):
    """
    Extract named entities and common words from text using NER.

    This function:
    1. Finds named entities (PERSON, LOC, ORG, GPE) with count >= min_count_ner
    2. Only with include_words: finds common words with count >= min_count_word
       and length >= min_word_length
    3. Excludes stop words and XML tags
    4. Merges overlapping entities (keeps longest)

    Args:
        text: Source text to analyze
        stop_words: Set of stop words to exclude (default: stop words of `lang`)
        min_count_ner: Minimum occurrences for NER entities (default: 5)
        min_count_word: Minimum occurrences for common words (default: 10)
        min_word_length: Minimum word length for common words (default: 5)
        include_words: Add frequent ordinary words besides named entities.
            None = DICT_FREQUENT_WORDS (off by default).
        lang: Source language for the default stop words (None = SOURCE_LANG)

    Returns:
        String with extracted terms (one per line), or None on error

    Format:
        Entity (CATEGORY)
        common_word
    """
    import gc

    if include_words is None:
        include_words = config.dict_frequent_words

    if config.debug:
        print("Starting Named Entity Recognition")
    if not text:
        if config.debug:
            print("No text to process.")
        return

    lang = lang or config.source_lang
    if stop_words is None:
        # NLTK + spaCy lists for the source language (see lexicon.get_stop_words)
        stop_words = lexicon.get_stop_words(lang)
        if config.debug:
            print(f"Using {len(stop_words)} stopwords for {lang}")
    else:
        stop_words = lexicon.normalize_words(stop_words)

    try:
        # Ensure PyTorch is using CUDA
        if not torch.cuda.is_available():
            if config.debug:
                print("CUDA is not available. Falling back to CPU.")
        else:
            if config.debug:
                print("CUDA is available. Using GPU.")

        # Prefer GPU usage in spaCy
        gpu = spacy.prefer_gpu()
        if config.debug:
            print(gpu)
        nlp = _get_nlp(config.nermodel, max_length=200000)

        # Split text into chunks (100k chars per chunk for balance of speed/memory)
        chunk_size = 100000
        text_chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        if config.debug:
            print(f"Split text into {len(text_chunks)} chunks of {chunk_size} chars each")

        ents = []

        for i, chunk in enumerate(text_chunks):
            try:
                # We only need NER here, so we can disable parser and lemmatizer to save time and avoid warnings
                doc = nlp(chunk, disable=_ner_disabled_pipes(lang))
                # No vector_norm filter here: languages with sparse word-vector
                # coverage (e.g. Korean, where particles attach to the entity
                # surface form) would have every entity's vector_norm come out
                # at 0, silently dropping the entire NER result.
                ents.extend([
                    (entity_text(ent), _normalize_label(ent.label_))
                    for ent in doc.ents if ent.label_ in NER_CATEGORIES
                ])

                if config.debug:
                    print(f"Chunk {i+1}/{len(text_chunks)}: Found {len(doc.ents)} entities (total: {len(ents)})")

                # Clean up to free memory between chunks
                del doc
                gc.collect()

            except Exception as e:
                if config.debug:
                    print(f"Error processing chunk {i+1}: {e}")
                continue

        # Count occurrences of each entity
        item_counts = Counter(ents)
        unique_ents = [(text, label, count)
                       for (text, label), count in item_counts.items()]

        if config.debug:
            print(f"Unique entities before filtering by count: {len(unique_ents)}")

        # Filter out entities with less than min_count_ner occurrences
        unique_ents = [ent for ent in unique_ents if ent[2] >= min_count_ner]

        if config.debug:
            print(f"Unique entities after filtering by count (min={min_count_ner}): {len(unique_ents)}")

        # Merge entities that contain substrings of other entities (Problem 1 fix)
        # Sort by length descending so longer entities are kept
        unique_ents.sort(key=lambda x: len(x[0]), reverse=True)
        final_merged_ents = []
        for ent in unique_ents:
            ent_lower = ent[0].lower()
            is_sub = False
            for existing in final_merged_ents:
                if ent_lower in existing[0].lower():
                    is_sub = True
                    break
            if not is_sub:
                final_merged_ents.append(ent)

        if config.debug:
            print(f"Unique entities after merging: {len(final_merged_ents)}")

        # Find most common words with count > min_count_word and length >= min_word_length
        # Sample first 5 chunks for word counting to save memory.
        # Skipped unless frequent words are requested (DICT_FREQUENT_WORDS).
        word_counts = Counter()
        for chunk in (text_chunks[:5] if include_words else []):
            try:
                doc = nlp(chunk, disable=["ner", "parser", "lemmatizer", "attribute_ruler"])

                # Regular words
                word_counts.update(
                    token.text.lower() for token in doc if token.is_alpha and not lexicon.is_stop_word(token.text, stop_words)
                )

                # Keywords by frequency: not stop words, alphabetic
                keywords_freq = [token.text.lower() for token in doc if not token.is_stop and token.is_alpha]
                word_counts.update(keywords_freq)

                # Keywords by semantic weight: not stop words, has vector representation
                keywords_semantic = [token.text.lower() for token in doc if not token.is_stop and token.vector_norm > 0]
                word_counts.update(keywords_semantic)

                del doc
                gc.collect()
            except Exception as e:
                logger.debug(f"Skipping word due to error: {e}")
                continue

    except Exception as e:
        if config.debug:
            print(f"Error loading spaCy model: {e}")
        return

    # Frequent words: count > min_count_word, length >= min_word_length, not a stop word
    filtered_words_with_counts = [(word, count) for word, count in word_counts.items()
                                   if count > min_count_word and len(word) >= min_word_length
                                   and not lexicon.is_stop_word(word, stop_words)]

    sorted_common_words_with_counts = sorted(filtered_words_with_counts, key=lambda x: x[1], reverse=True)
    top_common_words = [word for word, count in sorted_common_words_with_counts]

    if config.debug:
        print(f"Top common words with counts (min={min_count_word}, len>={min_word_length}): {sorted_common_words_with_counts[:20]}")

    # Normalize final_merged_ents
    seen_entities = set()
    normalized_final_merged_ents = []
    for ent in final_merged_ents:
        normalized_text = ent[0].strip().lower()
        if normalized_text not in seen_entities and not lexicon.is_stop_word(normalized_text, stop_words):
            seen_entities.add(normalized_text)
            normalized_final_merged_ents.append((ent[0], ent[1]))

    # Normalize top_common_words
    seen_words = set()
    normalized_top_common_words = []
    for word in top_common_words:
        normalized_word = word.strip().lower()
        if normalized_word not in seen_entities and not lexicon.is_stop_word(normalized_word, stop_words):
            seen_words.add(normalized_word)
            normalized_top_common_words.append(word)

    # Remove words from top_common_words that are substrings of entities
    for ent in final_merged_ents:
        words_in_ent = ent[0].strip().lower().split()
        for word in words_in_ent:
            if word in seen_words and not lexicon.is_stop_word(word, stop_words):
                seen_words.remove(word)

    unique_top_common_words = [word for word in normalized_top_common_words if word.lower() in seen_words]

    result_list = [f"{text} ({label})" for text, label in normalized_final_merged_ents] + unique_top_common_words

    if config.debug:
        print("Finished processing.")
    return '\n'.join(result_list) + '\n'


def create_dictionary_from_text(text, stop_words=None, min_count_ner=5, min_count_word=10, min_word_length=5,
                                include_words=None, lang=None):
    """
    Create dictionary from text using NER.

    Similar to make_vocab() but returns structured data for .dic file format.

    Args:
        text: Source text to analyze
        stop_words: Set of stop words to exclude
        min_count_ner: Minimum occurrences for NER entities
        min_count_word: Minimum occurrences for common words
        min_word_length: Minimum word length for common words
        include_words: Add frequent ordinary words (None = DICT_FREQUENT_WORDS, off by default)
        lang: Source language for the default stop words (None = SOURCE_LANG)

    Returns:
        List of tuples: [(source_term, category, notes), ...]
        - For NER entities: ("Alice", "PERSON", "")
        - For common words: ("wonderland", "TERM", "frequent word")
    """
    if not text:
        return []

    # Use make_vocab to get extracted terms
    extracted = make_vocab(text, stop_words, min_count_ner, min_count_word, min_word_length,
                           include_words=include_words, lang=lang)

    if not extracted:
        return []

    # Parse extracted terms into structured format
    result = []
    for line in extracted.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Check if it's an entity with category: "Term (CATEGORY)"
        match = re.match(r'^(.+?)\s*\(([^)]+)\)$', line)
        if match:
            term = match.group(1).strip()
            category = match.group(2).strip()
            result.append((term, category, ""))
        else:
            # Common word without category
            result.append((line, "TERM", "frequent word"))

    return result


# F4: cache of phrase vectors — the vocabulary does not change during a book
# translation, but every chunk used to re-run all dictionary words through
# spaCy. Word vectors of the loaded model are deterministic.
_PHRASE_VECTOR_CACHE = {}


def _to_numpy(vector):
    """A NumPy copy of a spaCy vector. Once load_spacy_model() has called
    spacy.prefer_gpu() with CuPy installed (extra [gpu]), the model keeps its
    vectors on the GPU and NumPy refuses to convert them implicitly — in the
    CPU matcher too."""
    return vector.get() if CUPY_AVAILABLE and isinstance(vector, cp.ndarray) else np.asarray(vector)


def _get_phrase_vector(phrase, nlp):
    """Mean vector of the phrase words (cached).

    Returns None (and caches it) when no word of the phrase has a vector.
    """
    if phrase in _PHRASE_VECTOR_CACHE:
        return _PHRASE_VECTOR_CACHE[phrase]
    sub_words = phrase.split()
    sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
    sub_vecs = [_to_numpy(d.vector) for d in sub_docs if d.vector_norm != 0]
    vec = np.mean(np.vstack(sub_vecs), axis=0) if sub_vecs else None
    _PHRASE_VECTOR_CACHE[phrase] = vec
    return vec


def _lemma_map(doc):
    """{normalized surface form: {normalized lemma, ...}} of a spaCy doc.

    Feeds lexicon.find_terms, so an inflected form in the chunk ("spiderguns",
    "паукопушками") matches the dictionary's base form. Empty when the
    pipeline has no lemmatizer.
    """
    lemmas = {}
    for token in doc:
        lemma = token.lemma_
        if not lemma or token.is_punct or token.is_space:
            continue
        surface, lemma = lexicon.normalize(token.text), lexicon.normalize(lemma)
        if lemma != surface:
            lemmas.setdefault(surface, set()).add(lemma)
    return lemmas


# spaCy models that failed to load/run during matching (not retried per chunk)
_UNUSABLE_MATCH_MODELS = set()


def _match_vocab_terms(text, vocab, lng, threshold, batch_size, xp):
    """
    Two-stage matching shared by the GPU (xp=cupy) and CPU (xp=numpy) entry points.

    spaCy runs once on the chunk and serves both stages:
    1. LEXICAL: lexicon.resolve_terms — word-sequence match on surface forms,
       Snowball stems and spaCy lemmas (wolves -> wolf), substring match for
       CJK and other unspaced scripts. Without a usable spaCy model the same
       search runs on surface forms and stems only.
    2. COSINE: word vectors of the chunk vs. mean vectors of the terms still
       unmatched (semantically close words).
    """
    if not text or not vocab:
        return []

    terms = [entry[lng] for entry in vocab.values() if entry.get(lng)]

    # SystemExit: spacy.cli.download exits the interpreter when it fails.
    if config.nermodel in _UNUSABLE_MATCH_MODELS:
        return lexicon.find_terms(text, terms, lng)
    try:
        if xp is not np:
            spacy.prefer_gpu()
        nlp = _get_nlp(config.nermodel, max_length=200000)
        doc = nlp(text, disable=["ner", "parser"])
    except (Exception, SystemExit) as e:
        # Reported once; later chunks go straight to the lexical result
        _UNUSABLE_MATCH_MODELS.add(config.nermodel)
        logger.warning(f"spaCy model {config.nermodel} unavailable, dictionary matching "
                       f"continues without lemmas/word vectors: {e}")
        return lexicon.find_terms(text, terms, lng)

    found, shadowed = lexicon.resolve_terms(text, terms, lng, _lemma_map(doc))
    matched, shadowed = set(found), set(shadowed)
    if config.debug:
        print(f"  Lexical matches: {sorted(matched)}")
    # A term covered by a longer one ("Hatter" inside "Mad Hatter") must not
    # come back through word vectors: the token "hatter" is its own best match
    unmatched = [t for t in terms if t not in matched and t not in shadowed]
    if not unmatched:
        return list(matched)

    valid_vocab_words = []
    vocab_vectors = []
    for phrase in unmatched:
        mean_vec = _get_phrase_vector(phrase, nlp)
        if mean_vec is not None:
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)
    if not vocab_vectors:
        return list(matched)

    vocab_matrix = xp.asarray(np.vstack(vocab_vectors))
    vocab_matrix = vocab_matrix / xp.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        token_vectors = xp.asarray(np.vstack([_to_numpy(t.vector) for t in tokens[i:i + batch_size]]))
        token_vectors = token_vectors / xp.linalg.norm(token_vectors, axis=1, keepdims=True)
        sims = xp.dot(token_vectors, vocab_matrix.T)
        for _, vi in zip(*xp.where(sims > threshold)):
            matched.add(valid_vocab_words[int(vi)])

    if config.debug:
        print(f"Found matching words: {matched}")
    return list(matched)


def known_words(words):
    """The one-word entries of `words` the spaCy model has a word vector for.

    A coined word ("spidergun") has none, an ordinary one ("starship") does,
    so this filters dictionary candidates. Empty when the model has no
    vectors (*_sm) or cannot be loaded: nothing is filtered then.
    """
    if config.nermodel in _UNUSABLE_MATCH_MODELS:
        return set()
    try:
        vocab = _get_nlp(config.nermodel, max_length=200000).vocab
    except (Exception, SystemExit) as e:
        _UNUSABLE_MATCH_MODELS.add(config.nermodel)
        logger.warning(f"spaCy model {config.nermodel} unavailable, dictionary terms are not "
                       f"checked against its vocabulary: {e}")
        return set()
    if not len(vocab.vectors):
        return set()
    return {w for w in words
            if len(w.split()) == 1 and (vocab.has_vector(w) or vocab.has_vector(w.lower()))}


def find_matching_words_with_cosine_similarity(text, vocab, lng, threshold=0.8, batch_size=1024):
    """
    Find vocabulary terms in text (GPU-accelerated cosine stage, needs CuPy).

    Args:
        text: Source text to search in
        vocab: Vocabulary dictionary {key: {lng: source_term, ...}}
        lng: Source language (name or code) — also the key of source terms
        threshold: Cosine similarity threshold (0.0-1.0)
        batch_size: Batch size for processing tokens

    Returns:
        List of matched vocabulary terms
    """
    if not CUPY_AVAILABLE:
        raise RuntimeError("CuPy is required for GPU processing. Use the CPU variant instead.")
    return _match_vocab_terms(text, vocab, lng, threshold, batch_size, cp)


def find_matching_words_with_cosine_similarity_cpu(text, vocab, lng, threshold=0.8, batch_size=256):
    """CPU (NumPy) variant of find_matching_words_with_cosine_similarity."""
    return _match_vocab_terms(text, vocab, lng, threshold, batch_size, np)


def extract_text_from_book(book_path: str) -> str:
    """
    Extract text content from book file.

    Args:
        book_path: Path to .fb2/.epub/.txt file

    Returns:
        Extracted text content
    """
    from pathlib import Path
    from src import fb2_handler, epub_handler, txt_handler

    ext = Path(book_path).suffix.lower()
    if ext == '.fb2':
        body, header, footer = fb2_handler.parse_xml(book_path)
        return body
    elif ext == '.epub':
        body, header, footer = epub_handler.parse_epub(book_path)
        return body
    elif ext == '.txt':
        body, header, footer = txt_handler.parse_txt(book_path)
        return body
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _merge_overlapping_entities(entities):
    """
    Merge overlapping entities - keep only highest count form.

    For example: ["John", "John Smith", "Smith"] -> ["John Smith"]
    Also merges case-insensitive: ["Gant", "gant"] -> single entry

    Args:
        entities: List of (term, category, count) tuples

    Returns:
        Merged list with duplicate/substring entities removed
    """
    if not entities:
        return entities

    # Step 1: Deduplicate exact matches (case-insensitive) - keep highest count
    normalized_groups = {}
    for term, cat, count in entities:
        key = term.lower()
        if key not in normalized_groups:
            normalized_groups[key] = (term, cat, count)
        else:
            # Keep highest count for exact duplicates
            if count > normalized_groups[key][2]:
                normalized_groups[key] = (term, cat, count)

    deduped = list(normalized_groups.values())

    # Step 2: Merge substrings - keep LONGEST form (not highest count)
    # Sort by length descending (longest first)
    sorted_by_length = sorted(deduped, key=lambda x: len(x[0]), reverse=True)

    merged = []
    for term, cat, count in sorted_by_length:
        term_lower = term.lower()
        # Check if this term is substring of any already-kept LONGER term
        is_substring = False
        for kept_term, _, _ in merged:
            kept_lower = kept_term.lower()
            # Skip if this term is substring of kept (and not equal)
            if term_lower != kept_lower and term_lower in kept_lower:
                is_substring = True
                break

        if not is_substring:
            merged.append((term, cat, count))

    # Sort by count descending for output
    return sorted(merged, key=lambda x: -x[2])

def _parse_vocabulary_response(vocab_translated: str, original_terms: str = "") -> dict:
    """
    Robustly parse vocabulary translation response with multiple strategies.
    Returns dict mapping source_lower -> (target, category)
    """
    import json
    import re

    # Parse original terms to extract categories if provided
    original_categories = {}
    if original_terms:
        for line in original_terms.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Extract term and category from NER output format "Term [CATEGORY]"
            match = re.match(r'^(.+?)\s*\[([^\]]+)\]$', line)
            if match:
                term = match.group(1).strip().lower()
                category = match.group(2).strip()
                original_categories[term] = category
            else:
                # Common word without category
                original_categories[line.lower()] = ''

    translations = {}
    categories_from_llm = {}

    # Strategy 1: Full JSON object/array parsing
    try:
        data = json.loads(vocab_translated.strip())
        if isinstance(data, dict) and 'terms' in data:
            terms = data['terms']
        elif isinstance(data, list):
            terms = data
        else:
            raise ValueError("Invalid JSON structure")

        for term in terms:
            if isinstance(term, dict):
                source = term.get('source', '').strip()
                target = term.get('target', '').strip()
                category = term.get('category', '').strip()
                if source and target:
                    translations[source.lower()] = target
                    if category:
                        categories_from_llm[source.lower()] = category
        print(f"Parsed {len(translations)} terms from JSON")
        return {k: (v, categories_from_llm.get(k, original_categories.get(k, ''))) for k, v in translations.items()}
    except (json.JSONDecodeError, ValueError, AttributeError):
        logger.debug("Strategy 1 JSON parse failed, trying array extraction", exc_info=True)

    # Strategy 2: Extract JSON array from response
    array_match = re.search(r'\[.*\]', vocab_translated.strip(), re.DOTALL)
    if array_match:
        try:
            terms = json.loads(array_match.group(0))
            for term in terms:
                if isinstance(term, dict):
                    source = term.get('source', '').strip()
                    target = term.get('target', '').strip()
                    category = term.get('category', '').strip()
                    if source and target:
                        translations[source.lower()] = target
                        if category:
                            categories_from_llm[source.lower()] = category
            print(f"Parsed {len(translations)} terms from extracted JSON array")
            return {k: (v, categories_from_llm.get(k, original_categories.get(k, ''))) for k, v in translations.items()}
        except (json.JSONDecodeError, ValueError, AttributeError):
            logger.debug("Strategy 2 JSON array parse failed, trying regex extraction", exc_info=True)

    # Strategy 3: Extract individual JSON objects
    term_pattern = r'\{\s*"source"\s*:\s*"([^"]*)"\s*,\s*"target"\s*:\s*"([^"]*)"(?:\s*,\s*"category"\s*:\s*"([^"]*)")?[^}]*\}'
    matches = re.findall(term_pattern, vocab_translated, re.DOTALL)
    for match in matches:
        source = match[0].strip()
        target = match[1].strip()
        category = match[2].strip() if len(match) > 2 else ''
        if source and target:
            translations[source.lower()] = target
            if category:
                categories_from_llm[source.lower()] = category

    if translations:
        print(f"Parsed {len(translations)} terms from individual JSON objects")
        return {k: (v, categories_from_llm.get(k, original_categories.get(k, ''))) for k, v in translations.items()}

    # Strategy 4: Fallback to line-based parsing (for CSV-like responses)
    for line in vocab_translated.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        if '=' in line:
            parts = line.split('=', 1)
            source = parts[0].strip()
            target_part = parts[1].strip()
            # Extract target before any comma
            target = target_part.split(',')[0].strip()
            if source and target:
                translations[source.lower()] = target

    if translations:
        print(f"Parsed {len(translations)} terms from line-based fallback")
        return {k: (v, original_categories.get(k, '')) for k, v in translations.items()}

    print("WARNING: No terms parsed from vocabulary response")
    return {}


def _lemma_keys(nlp, terms):
    """{term: normalized lemmas of all its tokens joined by spaces}.

    Batch lemmatization via nlp.pipe(). Uses every token, not just the first
    one — keying "John Smith" by "john" merged it with "John" and dropped the
    surname.
    """
    keys = {}
    for doc in nlp.pipe(list(terms), batch_size=256, disable=["ner", "parser"]):
        lemmas = [lexicon.normalize(t.lemma_ or t.text).strip() for t in doc if not t.is_space]
        keys[doc.text] = ' '.join(l for l in lemmas if l)
    return keys


def _preferred_form(forms, lemma_key):
    """Surface form to write into the .dic, with its original capitalization:
    the form that is its own lemma (nominative "Иван" over a more frequent
    "Ивана"), else the most frequent one ("Wells", whose lemma is "well")."""
    return max(forms, key=lambda f: (lexicon.normalize(f) == lemma_key, forms[f]))


def create_series_vocab(
    books_folder: str,
    output_file: str = "series.dic",
    min_count_ner: int = 2,
    min_count_word: int = 5,
    min_word_length: int = 3,
    include_words: Optional[bool] = None
) -> str:
    """
    Create unified dictionary from all books in folder.

    Workflow:
    1. Find all .fb2/.epub/.txt files in folder
    2. For each book: parse text → NER → collect terms
    3. Merge all terms into unified array (aggregate counts)
    4. Filter by min_count criteria
    5. Translate via LLM
    6. Save to .dic file

    Args:
        books_folder: Path to folder containing books
        output_file: Output .dic file path
        min_count_ner: Minimum occurrences for NER entities
        min_count_word: Minimum occurrences for common words
        min_word_length: Minimum word length for common words
        include_words: Add frequent ordinary words (None = DICT_FREQUENT_WORDS, off by default)

    Returns:
        Path to output file
    """
    import os
    import gc
    from pathlib import Path
    from collections import Counter

    stop_words = lexicon.get_stop_words(config.source_lang)
    print(f"Using {len(stop_words)} total stopwords")
    if include_words is None:
        include_words = config.dict_frequent_words

    # Resolve output_file relative to books_folder if it's just a filename
    if not os.path.dirname(output_file):
        # No directory in output_file, save to books_folder
        output_file = os.path.join(books_folder, output_file)

    # Find all book files
    supported_exts = {'.fb2', '.epub', '.txt'}
    book_files = []
    for f in os.listdir(books_folder):
        if Path(f).suffix.lower() in supported_exts:
            book_files.append(os.path.join(books_folder, f))

    if not book_files:
        raise ValueError(f"No book files found in {books_folder}")

    print(f"Found {len(book_files)} books")

    # Aggregate terms from all books - use RAW spaCy without make_vocab merging
    all_raw_entities = []  # [(text, label, book_name), ...] - raw counts
    all_words = Counter()  # word -> count
    book_names = {}  # book_path -> book_name

    # Load spaCy model once for all books
    nlp = _get_nlp(config.nermodel, max_length=200000)

    for book_path in book_files:
        book_name = Path(book_path).stem
        book_names[book_path] = book_name

        print(f"Processing: {book_name}")

        # Error handling for book parsing
        try:
            text = extract_text_from_book(book_path)
        except Exception as e:
            print(f"  Error reading {book_name}: {e}")
            continue

        # Split into chunks for processing
        chunk_size = 100000
        text_chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        for chunk_idx, chunk in enumerate(text_chunks):
            try:
                # Direct NER without make_vocab's merging
                doc = nlp(chunk, disable=_ner_disabled_pipes())

                # Collect raw entities with their labels (see make_vocab() for
                # why vector_norm is not used to filter entities, and
                # NER_CATEGORIES for why the label list isn't OntoNotes-only)
                for ent in doc.ents:
                    if ent.label_ in NER_CATEGORIES:
                        all_raw_entities.append((entity_text(ent), _normalize_label(ent.label_), book_name))

                if not include_words:
                    del doc
                    continue

                # Collect words (case-insensitive)
                for token in doc:
                    if token.is_alpha and not lexicon.is_stop_word(token.text, stop_words):
                        word_key = token.text.lower()
                        all_words[word_key] += 1

                # Keywords by frequency: not stop words, alphabetic
                keywords_freq = [token.text.lower() for token in doc if not token.is_stop and token.is_alpha]
                for kw in keywords_freq:
                    all_words[kw] += 1

                # Keywords by semantic weight: not stop words, has vector representation
                keywords_semantic = [token.text.lower() for token in doc if not token.is_stop and token.vector_norm > 0]
                for kw in keywords_semantic:
                    all_words[kw] += 1

                del doc
            except Exception as e:
                print(f"  Error processing chunk {chunk_idx}: {e}")
                continue

        # Force garbage collection after each book
        gc.collect()

        print(f"  Raw entities collected: {len(all_raw_entities)} (cumulative)")

    print(f"\nTotal raw entities: {len(all_raw_entities)}")
    print(f"Total unique words: {len(all_words)}")

    # ============================================================
    # PHASE 1: NORMALIZE & MERGE ENTITIES (by lemma only, keep FIRST category)
    # ============================================================

    # Group surface forms of an entity by the lemmas of ALL its tokens
    # ("Ивана"/"Иван" together, "John Smith" stays "John Smith"), keep the
    # first category seen, and write the most frequent surface form: proper
    # names keep their capital letters in the .dic.
    entity_groups = {}  # lemma key -> (first_category, Counter(surface form))
    term_to_key = _lemma_keys(nlp, {term for term, _, _ in all_raw_entities})

    for term, cat, book in all_raw_entities:
        key = term_to_key.get(term) or lexicon.normalize(term)
        if key not in entity_groups:
            entity_groups[key] = (cat, Counter())
        entity_groups[key][1][term] += 1

    aggregated_entities = []
    for key, (first_cat, forms) in entity_groups.items():
        output_term = _preferred_form(forms, key)
        aggregated_entities.append((output_term, first_cat, sum(forms.values())))

    print(f"\nEntities after lemma-based merge (first category): {len(aggregated_entities)}")

    # ============================================================
    # PHASE 2: NORMALIZE & MERGE WORDS (by lemma, case-insensitive)
    # ============================================================

    # Re-process words with lemmatization
    word_groups = {}  # lemma -> [(word, count), ...]

    word_to_lemma = _lemma_keys(nlp, all_words.keys())

    for word, count in all_words.items():
        lemma = word_to_lemma.get(word) or word.lower().strip()

        if lemma not in word_groups:
            word_groups[lemma] = []
        word_groups[lemma].append((word, count))

    # Aggregate word counts by lemma
    # Output lemma in lowercase (infinitive form)
    aggregated_words = []
    for lemma, entries in word_groups.items():
        total_count = sum(e[1] for e in entries)
        # Use lowercase lemma as output term
        output_term = lemma.lower()
        aggregated_words.append((output_term, total_count))

    print(f"Words after lemma-based merge: {len(aggregated_words)}")

    # ============================================================
    # PHASE 3: FILTER BY MIN COUNT & MERGE OVERLAPPING
    # ============================================================

    # Filter entities by min_count_ner
    filtered_entities = [
        (term, cat, count)
        for term, cat, count in aggregated_entities
        if count >= min_count_ner
    ]
    filtered_entities = sorted(filtered_entities, key=lambda x: -x[2])

    # Entity merging - remove substring entities (keep longest form)
    filtered_entities = _merge_overlapping_entities(filtered_entities)

    # Filter words by min_count_word and min_word_length
    filtered_words = [
        (word, count)
        for word, count in aggregated_words
        if count >= min_count_word and len(word) >= min_word_length
    ]
    filtered_words = sorted(filtered_words, key=lambda x: -x[1])

    # ============================================================
    # PHASE 3b: REMOVE DUPLICATES - filter out words that appear in entities
    # ============================================================
    entity_term_set = {term.lower() for term, _, _ in filtered_entities}
    filtered_words = [(w, c) for w, c in filtered_words if w.lower() not in entity_term_set]

    # Free memory
    del all_words

    print(f"Filtered entities (after merge): {len(filtered_entities)}")
    print(f"Filtered words: {len(filtered_words)}")

    # If no terms, return early
    if not filtered_entities and not filtered_words:
        print("No terms found")
        return output_file

    # Prepare terms for translation with category (if available)
    terms_for_translation = []

    for term, category, count in filtered_entities:
        # Format: term [CATEGORY] (NER entities always have category)
        terms_for_translation.append(f"{term} [{category}]")

    for word, count in filtered_words:
        # Words without category - no brackets
        terms_for_translation.append(word)

    if not terms_for_translation:
        print("No terms to translate")
        return output_file

    print(f"Terms for translation: {len(terms_for_translation)}")
    terms_text = '\n'.join(terms_for_translation)

    # Ensure output directory exists
    import os
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")

    # Split into smaller chunks to avoid 500 errors from LLM API
    # Current: ~16K chars → too large for vocabulary endpoint
    # Target: ~4K chars per chunk (safe for most LLMs)
    CHUNK_SIZE = 4096
    lines = terms_text.split('\n')
    chunks = []
    current = []
    current_len = 0
    for line in lines:
        current.append(line)
        current_len += len(line) + 1
        if current_len >= CHUNK_SIZE:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0
    if current:
        chunks.append('\n'.join(current))

    print(f"Split into {len(chunks)} translation chunk(s) (CHUNK_SIZE={CHUNK_SIZE})")

    from src import utils as ta

    # Track all parsed translations for final grouped output
    all_translations = {}  # source_lower -> target
    all_categories = {}    # source_lower -> category
    total_parsed = 0

    def parse_chunk_response(vocab_translated, translations, categories, original_terms=""):
        """Parse a single chunk's JSON response into translations dict using robust parsing."""
        try:
            # Use the robust parsing function
            parsed_dict = _parse_vocabulary_response(vocab_translated, original_terms)
            parsed = 0
            
            for source_lower, (target, category) in parsed_dict.items():
                translations[source_lower] = target
                categories[source_lower] = category
                parsed += 1
                
            return parsed
                
        except Exception as e:
            print(f"  Robust parse error: {e}")
            return 0

    # Collected in memory and written in one atomic step at the end: a failure
    # mid-way (LLM error, Ctrl-C) must not leave a half-written .dic that a
    # later run would take for a finished dictionary.
    out_lines = [
        "# Vocabulary for series\n",
        "# Format: source = target, category, gender, notes\n",
        "# Generated by create_series_vocab\n\n",
    ]

    for idx, chunk in enumerate(chunks):
        print(f"Translating chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")

        vocab_translated = ta.vocabulary(
            config.source_lang,
            config.target_lang,
            chunk,
            config.country,
            "proofread"
        )

        if config.debug:
            print(f"  LLM response: {len(vocab_translated)} chars")

        chunk_parsed = parse_chunk_response(vocab_translated, all_translations, all_categories, chunk)
        total_parsed += chunk_parsed

        out_lines.append(f"\n# --- Chunk {idx + 1}/{len(chunks)} ---\n")
        for term_text in chunk.split('\n'):
            term_text = term_text.strip()
            if not term_text:
                continue
            # Extract term and NER category from format "term [CATEGORY]"
            ner_cat = ""
            m = re.match(r'^(.+?)\s+\[([A-Z]+)\]$', term_text)
            if m:
                term_text = m.group(1).strip()
                ner_cat = m.group(2)

            term_lower = term_text.lower()
            target = all_translations.get(term_lower, "")
            category = all_categories.get(term_lower, ner_cat)
            out_lines.append(f"{term_text} = {target}, {category}, , \n")

        print(f"  Chunk {idx + 1} translated ({chunk_parsed} terms)")

    tmp_path = f"{output_file}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)
    os.replace(tmp_path, output_file)

    print(f"Total parsed: {total_parsed} terms across {len(chunks)} chunk(s)")
    print(f"Dictionary saved to: {output_file}")
    return output_file
