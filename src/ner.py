from collections import Counter
import logging
import re
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

logger = logging.getLogger(__name__)

# Initialize config
config = Config()

# Module-level cache for spaCy models (Problem 3 fix)
_nlp_cache = {}

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

def make_vocab(text, stop_words=None, min_count_ner=5, min_count_word=10, min_word_length=5):
    """
    Extract named entities and common words from text using NER.

    This function:
    1. Finds named entities (PERSON, LOC, ORG, GPE) with count >= min_count_ner
    2. Finds common words with count >= min_count_word and length >= min_word_length
    3. Excludes stop words and XML tags
    4. Merges overlapping entities (keeps longest)

    Args:
        text: Source text to analyze
        stop_words: Set of stop words to exclude (default: common English + XML tags)
        min_count_ner: Minimum occurrences for NER entities (default: 5)
        min_count_word: Minimum occurrences for common words (default: 10)
        min_word_length: Minimum word length for common words (default: 5)

    Returns:
        String with extracted terms (one per line), or None on error

    Format:
        Entity (CATEGORY)
        common_word
    """
    import gc

    if config.debug:
        print("Starting Named Entity Recognition")
    if not text:
        if config.debug:
            print("No text to process.")
        return

    # Try to load NLTK stopwords (top ~200 words), fallback to manual list
    # NLTK stopwords are high-frequency words that are usually not meaningful for vocabulary
    default_stop_words = set()

    try:
        import nltk
        try:
            from nltk.corpus import stopwords
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)
        default_stop_words = set(stopwords.words('english'))
        if config.debug:
            print(f"Loaded {len(default_stop_words)} NLTK stopwords")
    except ImportError:
        if config.debug:
            print("NLTK not available, using manual stopwords list")
        # Fallback manual list (NLTK english stopwords)
        default_stop_words = set([
            "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
            "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her",
            "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs",
            "themselves", "what", "which", "who", "whom", "this", "that", "these", "those",
            "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
            "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
            "or", "because", "as", "until", "while", "of", "at", "by", "for", "with",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over",
            "under", "again", "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
            "very", "s", "t", "can", "will", "just", "don", "should", "now",
            # Additional common words from books
            "d", "ll", "m", "re", "ve", "said", "would", "could", "upon", "must", "might",
            "yet", "thing", "things", "way", "ways", "like", "even", "also", "back", "still",
            "much", "get", "got", "go", "went", "come", "came", "see", "saw", "know", "knew",
            "think", "thought", "want", "wanted", "take", "took", "give", "gave", "make", "made",
            "first", "second", "one", "two", "time", "times", "new", "old", "great", "little",
            # Book/format specific
            "chapter", "part", "book", "volume", "section", "page", "p", "title", "author",
            # Common verbs to filter
            "said", "ask", "asked", "say", "tell", "told", "look", "looked", "seem", "seemed",
            "feel", "felt", "leave", "left", "call", "called", "turn", "turned", "get", "got",
            "inside", "emphasis",
        ])

    # Add custom stopwords that are common in books but not in NLTK list
    custom_stop_words = {
        "p", "section", "chapter", "part", "book", "volume", "title", "author", "name",
        "emphasis", "inside", "asked", "would", "could", "shall", "may", "might", "must",
        "every", "any", "another", "such", "however", "though", "although", "because",
        "therefore", "since", "without", "within", "around", "toward", "towards", "upon",
        "ever", "never", "always", "often", "sometimes", "usually", "again", "already",
        "yet", "still", "perhaps", "maybe", "certainly", "exactly", "especially",
    }
    default_stop_words.update(custom_stop_words)

    if stop_words is None:
        stop_words = default_stop_words
        if config.debug:
            print(f"Using {len(stop_words)} total stopwords (NLTK + custom)")
    else:
        stop_words = set(stop_words)

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

        ner_category = ["ORG", "LOC", "GPE", "PERSON", "EVENT", "FAC", "PRODUCT"]
        ents = []

        for i, chunk in enumerate(text_chunks):
            try:
                # We only need NER here, so we can disable parser and lemmatizer to save time and avoid warnings
                doc = nlp(chunk, disable=["parser", "lemmatizer", "attribute_ruler"])
                ents.extend([
                    (ent.text.strip(), ent.label_)
                    for ent in doc.ents if ent.vector_norm != 0 and ent.label_ in ner_category
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
        unique_ents = [ent for ent in unique_ents if ent[3] >= min_count_ner]

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
        # Sample first 5 chunks for word counting to save memory
        word_counts = Counter()
        for chunk in text_chunks[:5]:  # Sample first 5 chunks for word counting
            try:
                doc = nlp(chunk, disable=["ner", "parser", "lemmatizer", "attribute_ruler"])

                # Regular words
                word_counts.update(
                    token.text.lower() for token in doc if token.is_alpha and token.text.lower() not in stop_words
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

    # Filter words with count > min_count_word and length >= min_word_length
    filtered_words_with_counts = [(word, count) for word, count in word_counts.items() if count > min_count_word and len(word) >= min_word_length]

    sorted_common_words_with_counts = sorted(filtered_words_with_counts, key=lambda x: x[1], reverse=True)
    top_common_words = [word for word, count in sorted_common_words_with_counts]

    if config.debug:
        print(f"Top common words with counts (min={min_count_word}, len>={min_word_length}): {sorted_common_words_with_counts[:20]}")

    # Normalize final_merged_ents
    seen_entities = set()
    normalized_final_merged_ents = []
    for ent in final_merged_ents:
        normalized_text = ent[0].strip().lower()
        if normalized_text not in seen_entities and normalized_text not in stop_words:
            seen_entities.add(normalized_text)
            normalized_final_merged_ents.append((ent[0], ent[1]))

    # Normalize top_common_words
    seen_words = set()
    normalized_top_common_words = []
    for word in top_common_words:
        normalized_word = word.strip().lower()
        if normalized_word not in seen_entities and normalized_word not in stop_words:
            seen_words.add(normalized_word)
            normalized_top_common_words.append(word)

    # Remove words from top_common_words that are substrings of entities
    for ent in final_merged_ents:
        words_in_ent = ent[0].strip().lower().split()
        for word in words_in_ent:
            if word in seen_words and word not in stop_words:
                seen_words.remove(word)

    # Filter words with count > min_count_word, length >= min_word_length, and not in stop_words
    filtered_words_with_counts = [(word, count) for word, count in word_counts.items()
                                   if count > min_count_word and len(word) >= min_word_length
                                   and word.lower() not in stop_words]

    sorted_common_words_with_counts = sorted(filtered_words_with_counts, key=lambda x: x[1], reverse=True)
    top_common_words = [word for word, count in sorted_common_words_with_counts]

    if config.debug:
        print(f"Top common words with counts (min={min_count_word}, len>={min_word_length}): {sorted_common_words_with_counts[:20]}")

    # Normalize final_merged_ents
    seen_entities = set()
    normalized_final_merged_ents = []
    for ent in final_merged_ents:
        normalized_text = ent[0].strip().lower()
        if normalized_text not in seen_entities and normalized_text not in stop_words:
            seen_entities.add(normalized_text)
            normalized_final_merged_ents.append((ent[0], ent[1]))

    # Normalize top_common_words
    seen_words = set()
    normalized_top_common_words = []
    for word in top_common_words:
        normalized_word = word.strip().lower()
        if normalized_word not in seen_entities and normalized_word not in stop_words:
            seen_words.add(normalized_word)
            normalized_top_common_words.append(word)

    # Remove words from top_common_words that are substrings of entities
    for ent in final_merged_ents:
        words_in_ent = ent[0].strip().lower().split()
        for word in words_in_ent:
            if word in seen_words and word not in stop_words:
                seen_words.remove(word)

    unique_top_common_words = [word for word in normalized_top_common_words if word.lower() in seen_words]

    result_list = [f"{text} ({label})" for text, label in normalized_final_merged_ents] + unique_top_common_words

    if config.debug:
        print("Finished processing.")
    return '\n'.join(result_list) + '\n'


def extract_keywords_from_text(text: str, nlp=None, stop_words: set = None) -> list[str]:
    """
    Extract keywords from text using spaCy.

    Two extraction strategies:
    1. Frequency-based: tokens that are not stop words and are alphabetic
    2. Semantic: tokens that are not stop words and have non-zero vector norm

    Returns a combined unique list of keyword strings (preserving original case).

    Args:
        text: Source text to extract keywords from
        nlp: Pre-loaded spaCy pipeline (will load if None)
        stop_words: Set of stop words to exclude (default: common English words)

    Returns:
        List of unique keyword strings
    """
    default_stop = {
        "the", "and", "p", "emphasis", "section", "first", "second", "one", "two",
        "chapter", "part", "book", "volume", "title", "author", "name", "said",
        "like", "just", "know", "think", "see", "look", "come", "take", "give",
        "make", "find", "tell", "ask", "work", "seem", "feel", "try", "leave", "call"
    }

    if stop_words is None:
        stop_words = default_stop

    try:
        if nlp is None:
            nlp = _get_nlp(config.nermodel, max_length=200000)

        # Split into chunks for large texts
        chunk_size = 100000
        text_chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        all_freq_keywords = []
        all_semantic_keywords = []

        for chunk in text_chunks:
            try:
                doc = nlp(chunk, disable=["ner", "parser", "lemmatizer", "attribute_ruler"])

                # Frequency-based keywords: alpha tokens that are not stop words
                freq_kw = [token.text for token in doc if not token.is_stop and token.is_alpha]
                all_freq_keywords.extend(freq_kw)

                # Semantic keywords: non-stop tokens with meaningful vector representation
                semantic_kw = [token.text for token in doc if not token.is_stop and token.vector_norm > 0]
                all_semantic_keywords.extend(semantic_kw)

                del doc
            except Exception as e:
                if config.debug:
                    print(f"Keyword extraction chunk error: {e}")
                continue

        # Combine both lists, preserving order, deduplicating while keeping first occurrence
        seen = set()
        combined = []
        for kw in all_freq_keywords + all_semantic_keywords:
            if kw not in seen:
                seen.add(kw)
                combined.append(kw)

        return combined

    except Exception as e:
        if config.debug:
            print(f"Keyword extraction failed: {e}")
        return []


def create_dictionary_from_text(text, stop_words=None, min_count_ner=5, min_count_word=10, min_word_length=5):
    """
    Create dictionary from text using NER.

    Similar to make_vocab() but returns structured data for .dic file format.

    Args:
        text: Source text to analyze
        stop_words: Set of stop words to exclude
        min_count_ner: Minimum occurrences for NER entities
        min_count_word: Minimum occurrences for common words
        min_word_length: Minimum word length for common words

    Returns:
        List of tuples: [(source_term, category, notes), ...]
        - For NER entities: ("Alice", "PERSON", "")
        - For common words: ("wonderland", "TERM", "frequent word")
    """
    if not text:
        return []

    # Use make_vocab to get extracted terms
    extracted = make_vocab(text, stop_words, min_count_ner, min_count_word, min_word_length)

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


def find_matching_words_with_cosine_similarity(text, vocab, lng, threshold=0.8, batch_size=1024):
    """
    Find vocabulary terms in text using cosine similarity (GPU-accelerated).

    Uses CuPy for GPU acceleration when available.

    Args:
        text: Source text to search in
        vocab: Vocabulary dictionary {key: {lng: source_term, ...}}
        lng: Language code for source terms
        threshold: Cosine similarity threshold (0.0-1.0)
        batch_size: Batch size for processing tokens

    Returns:
        List of matched vocabulary terms
    """
    if not CUPY_AVAILABLE:
        raise RuntimeError("CuPy is required for GPU processing. Use the CPU variant instead.")

    if config.debug:
        print("Starting cosine similarity matching (GPU)")

    if not text or not vocab:
        if config.debug:
            print("No text or vocabulary to process.")
        return []

    matched_words_set = set()

    # STAGE 1: TEXT SEARCH (exact match) — Problem 2 fix: pre-compile patterns
    # ==================================
    text_lower = text.lower()

    compiled_patterns = [
        (re.compile(r'\b' + re.escape(entry.get(lng, "").lower()) + r'\b'), entry.get(lng, ""))
        for entry in vocab.values()
        if entry.get(lng, "")
    ]
    for pattern, source_term in compiled_patterns:
        if pattern.search(text_lower):
            matched_words_set.add(source_term)
            if config.debug:
                print(f"  Text match: '{source_term}' found in chunk")

    # STAGE 2: COSINE SEARCH (semantic)
    # =================================
    # Filter vocab: only terms NOT already matched by text search
    unmatched_vocab = {
        k: v for k, v in vocab.items() 
        if v.get(lng, "") not in matched_words_set
    }

    if not unmatched_vocab:
        if config.debug:
            print(f"All terms matched by text search: {len(matched_words_set)}")
        return list(matched_words_set)

    try:
        spacy.prefer_gpu()
        nlp = _get_nlp(config.nermodel, max_length=200000)
        # For cosine similarity, we only need vectors. Disable everything else to avoid W108 and other warnings.
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"Error loading spaCy model: {e}")
        return []

    orig_values = [entry[lng] for entry in unmatched_vocab.values() if lng in entry]

    valid_vocab_words = []
    vocab_vectors = []

    for phrase in orig_values:
        sub_words = phrase.split()
        # Disable all components that are not needed for vector generation
        sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
        sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]

        if sub_vecs:
            mean_vec = np.mean(np.vstack(sub_vecs), axis=0)
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)

    if not vocab_vectors:
        if config.debug:
            print("No valid vectors in vocab.")
        return list(matched_words_set)  # Return Stage 1 matches

    # numpy -> cupy (GPU acceleration)
    vocab_matrix = cp.asarray(np.vstack(vocab_vectors))
    vocab_matrix = vocab_matrix / cp.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    # Don't reset matched_words_set - keep Stage 1 matches
    # matched_words_set = set()

    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i+batch_size]
        token_vectors = np.vstack([t.vector for t in batch_tokens])
        token_vectors = cp.asarray(token_vectors)
        token_vectors = token_vectors / cp.linalg.norm(token_vectors, axis=1, keepdims=True)

        sims = cp.dot(token_vectors, vocab_matrix.T)

        best_matches = cp.where(sims > threshold)
        for _, vi in zip(*best_matches):
            matched_words_set.add(valid_vocab_words[int(vi)])

    if config.debug:
        print(f"Found matching words: {matched_words_set}")
    return list(matched_words_set)


def find_matching_words_with_cosine_similarity_cpu(text, vocab, lng, threshold=0.8, batch_size=256):
    """
    Two-stage matching (CPU version):
    1. TEXT SEARCH: Exact substring match (priority)
    2. COSINE SEARCH: Semantic similarity for remaining terms
    
    Uses NumPy instead of CuPy for systems without GPU.

    Args:
        text: Source text to search in
        vocab: Vocabulary dictionary {key: {lng: source_term, ...}}
        lng: Language code for source terms
        threshold: Cosine similarity threshold (0.0-1.0)
        batch_size: Batch size for processing tokens (smaller for CPU)

    Returns:
        List of matched vocabulary terms
    """
    if config.debug:
        print("Starting cosine similarity matching (CPU)")

    if not text or not vocab:
        if config.debug:
            print("No text or vocabulary to process.")
        return []

    matched_words_set = set()

    # STAGE 1: TEXT SEARCH (exact match) — Problem 2 fix: pre-compile patterns
    # ==================================
    text_lower = text.lower()

    compiled_patterns = [
        (re.compile(r'\b' + re.escape(entry.get(lng, "").lower()) + r'\b'), entry.get(lng, ""))
        for entry in vocab.values()
        if entry.get(lng, "")
    ]
    for pattern, source_term in compiled_patterns:
        if pattern.search(text_lower):
            matched_words_set.add(source_term)
            if config.debug:
                print(f"  Text match: '{source_term}' found in chunk")

    # STAGE 2: COSINE SEARCH (semantic)
    # =================================
    # Filter vocab: only terms NOT already matched by text search
    unmatched_vocab = {
        k: v for k, v in vocab.items() 
        if v.get(lng, "") not in matched_words_set
    }

    if not unmatched_vocab:
        if config.debug:
            print(f"All terms matched by text search: {len(matched_words_set)}")
        return list(matched_words_set)

    try:
        # CPU mode - don't call spacy.prefer_gpu()
        nlp = _get_nlp(config.nermodel, max_length=200000)
        # For cosine similarity, we only need vectors
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"Error loading spaCy model: {e}")
        return list(matched_words_set)

    orig_values = [entry[lng] for entry in unmatched_vocab.values() if lng in entry]

    valid_vocab_words = []
    vocab_vectors = []

    for phrase in orig_values:
        sub_words = phrase.split()
        sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]))
        sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]

        if sub_vecs:
            mean_vec = np.mean(np.vstack(sub_vecs), axis=0)
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)

    if not vocab_vectors:
        if config.debug:
            print("No valid vectors in vocab.")
        return list(matched_words_set)  # Return already matched terms from Stage 1

    # NumPy only (CPU) - no CuPy
    vocab_matrix = np.vstack(vocab_vectors)
    vocab_matrix = vocab_matrix / np.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    # Don't reset matched_words_set - keep Stage 1 matches
    # matched_words_set = set()

    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i+batch_size]
        token_vectors = np.vstack([t.vector for t in batch_tokens])
        token_vectors = token_vectors / np.linalg.norm(token_vectors, axis=1, keepdims=True)

        # NumPy dot product (CPU)
        sims = np.dot(token_vectors, vocab_matrix.T)

        # Find matches above threshold
        best_matches = np.where(sims > threshold)
        for _, vi in zip(*best_matches):
            matched_words_set.add(valid_vocab_words[int(vi)])

    if config.debug:
        print(f"Found matching words: {matched_words_set}")
    return list(matched_words_set)


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
        pass

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
            pass

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


def create_series_vocab(
    books_folder: str,
    output_file: str = "series.dic",
    min_count_ner: int = 2,
    min_count_word: int = 5,
    min_word_length: int = 3
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

    Returns:
        Path to output file
    """
    import os
    import gc
    from pathlib import Path
    from collections import Counter

    # Try to load NLTK stopwords (same as make_vocab)
    default_stop_words = set()

    try:
        import nltk
        try:
            from nltk.corpus import stopwords
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)
        default_stop_words = set(stopwords.words('english'))
        print(f"Loaded {len(default_stop_words)} NLTK stopwords")
    except ImportError:
        default_stop_words = set([
            "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
            "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her",
            "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs",
            "themselves", "what", "which", "who", "whom", "this", "that", "these", "those",
            "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
            "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
            "or", "because", "as", "until", "while", "of", "at", "by", "for", "with",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over",
            "under", "again", "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
            "very", "s", "t", "can", "will", "just", "don", "should", "now",
            "d", "ll", "m", "re", "ve", "said", "would", "could", "upon", "must", "might",
            "yet", "thing", "things", "way", "ways", "like", "even", "also", "back", "still",
            "much", "get", "got", "go", "went", "come", "came", "see", "saw", "know", "knew",
            "think", "thought", "want", "wanted", "take", "took", "give", "gave", "make", "made",
            "first", "second", "one", "two", "time", "times", "new", "old", "great", "little",
            "chapter", "part", "book", "volume", "section", "page", "p", "title", "author",
            "said", "ask", "asked", "say", "tell", "told", "look", "looked", "seem", "seemed",
            "feel", "felt", "leave", "left", "call", "called", "turn", "turned", "get", "got",
            "inside", "emphasis",
        ])

    # Add custom stopwords
    custom_stop_words = {
        "p", "section", "chapter", "part", "book", "volume", "title", "author", "name",
        "emphasis", "inside", "asked", "would", "could", "shall", "may", "might", "must",
        "every", "any", "another", "such", "however", "though", "although", "because",
        "therefore", "since", "without", "within", "around", "toward", "towards", "upon",
        "ever", "never", "always", "often", "sometimes", "usually", "again", "already",
        "yet", "still", "perhaps", "maybe", "certainly", "exactly", "especially",
    }
    default_stop_words.update(custom_stop_words)
    stop_words = default_stop_words
    print(f"Using {len(stop_words)} total stopwords")

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

    ner_category = ["ORG", "LOC", "GPE", "PERSON", "EVENT", "FAC", "PRODUCT"]

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
                doc = nlp(chunk, disable=["parser", "lemmatizer", "attribute_ruler"])

                # Collect raw entities with their labels
                for ent in doc.ents:
                    if ent.label_ in ner_category and ent.vector_norm != 0:
                        all_raw_entities.append((ent.text.strip(), ent.label_, book_name))

                # Collect words (case-insensitive)
                for token in doc:
                    if token.is_alpha and token.text.lower() not in stop_words:
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

    # Re-process raw entities with lemmatization enabled
    # Group by lemma ONLY, keep first encountered category (ignore later categories)
    entity_lemmas = {}  # lemma -> (first_category, [(term, count), ...])

    # Problem 4 fix: batch lemmatization using nlp.pipe()
    unique_terms = list(set(term for term, _, _ in all_raw_entities))
    term_to_lemma = {}
    for doc in nlp.pipe(unique_terms, batch_size=256, disable=["ner", "parser", "attribute_ruler"]):
        term_to_lemma[doc.text] = doc[0].lemma_.lower().strip() if doc else doc.text.lower().strip()

    for term, cat, book in all_raw_entities:
        lemma = term_to_lemma.get(term, term.lower().strip())

        if lemma not in entity_lemmas:
            # First encounter - store category
            entity_lemmas[lemma] = (cat, [(term, 1)])
        else:
            # Already seen - append term but keep first category
            first_cat, entries = entity_lemmas[lemma]
            entries.append((term, 1))

    # Aggregate counts per lemma, keep first category
    # Output lemma in lowercase (infinitive form) - e.g. "dragon" not "Dragon"
    aggregated_entities = []
    for lemma, (first_cat, entries) in entity_lemmas.items():
        total_count = sum(e[1] for e in entries)
        # Use lowercase lemma as output term (normalized form)
        output_term = lemma.lower()
        aggregated_entities.append((output_term, first_cat, total_count))

    print(f"\nEntities after lemma-based merge (first category): {len(aggregated_entities)}")

    # ============================================================
    # PHASE 2: NORMALIZE & MERGE WORDS (by lemma, case-insensitive)
    # ============================================================

    # Re-process words with lemmatization
    word_groups = {}  # lemma -> [(word, count), ...]

    # Problem 4 fix: batch lemmatization using nlp.pipe()
    unique_words = list(all_words.keys())
    word_to_lemma = {}
    for doc in nlp.pipe(unique_words, batch_size=256, disable=["ner", "parser", "attribute_ruler"]):
        word_to_lemma[doc.text] = doc[0].lemma_.lower().strip() if doc else doc.text.lower().strip()

    for word, count in all_words.items():
        lemma = word_to_lemma.get(word, word.lower().strip())

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
    import json as _json

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

    # Write header once
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Vocabulary for series\n")
        f.write(f"# Format: source = target, category, gender, notes\n")
        f.write(f"# Generated by create_series_vocab\n\n")

    # Translate each chunk and write immediately
    for idx, chunk in enumerate(chunks):
        print(f"Translating chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")

        vocab_translated = ta.vocabulary(
            config.source_lang,
            config.target_lang,
            chunk,
            config.country,
            "Translate"
        )

        if config.debug:
            print(f"  LLM response: {len(vocab_translated)} chars")

        chunk_parsed = parse_chunk_response(vocab_translated, all_translations, all_categories, chunk)
        total_parsed += chunk_parsed

        # Write this chunk's entries to file immediately (append)
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(f"\n# --- Chunk {idx + 1}/{len(chunks)} ---\n")
            for term_text in chunk.split('\n'):
                term_text = term_text.strip()
                if not term_text:
                    continue
                # Extract term and NER category from format "term [CATEGORY]"
                import re as _re
                ner_cat = ""
                m = _re.match(r'^(.+?)\s+\[([A-Z]+)\]$', term_text)
                if m:
                    term_text = m.group(1).strip()
                    ner_cat = m.group(2)

                term_lower = term_text.lower()
                target = all_translations.get(term_lower, "")
                category = all_categories.get(term_lower, ner_cat)

                if category:
                    gender = ""
                    f.write(f"{term_text} = {target}, {category}, {gender}, \n")
                else:
                    f.write(f"{term_text} = {target}, , , \n")

        print(f"  Chunk {idx + 1} written to file ({chunk_parsed} terms)")

    print(f"Total parsed: {total_parsed} terms across {len(chunks)} chunk(s)")
    print(f"Dictionary saved to: {output_file}")
    return output_file
