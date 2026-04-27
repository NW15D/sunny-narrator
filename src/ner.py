from collections import Counter
import re
import spacy
import spacy.cli
import torch
import numpy as np
import cupy as cp

from src.config import Config

# Initialize config
config = Config()

def load_spacy_model(model_name):
    """
    Attempts to load a spaCy model. If not found, downloads it and tries again.
    """
    try:
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

    # Define default stop words or use user provided
    default_stop_words = set([
        "the", "and", "p", "emphasis", "section", "first", "second", "one", "two",
        "chapter", "part", "book", "volume", "title", "author", "name", "said",
        "like", "just", "know", "think", "see", "look", "come", "take", "give",
        "make", "find", "tell", "ask", "work", "seem", "feel", "try", "leave", "call"
    ])

    if stop_words is None:
        stop_words = default_stop_words
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
        nlp = load_spacy_model(config.nermodel)
        
        # Increase max length limit for large documents
        nlp.max_length = 200000

        # Split text into chunks (100k chars per chunk for balance of speed/memory)
        chunk_size = 100000
        text_chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        if config.debug:
            print(f"Split text into {len(text_chunks)} chunks of {chunk_size} chars each")
        
        ner_category = ["ORG", "LOC", "GPE", "PERSON"]
        ents = []
        
        for i, chunk in enumerate(text_chunks):
            try:
                # We only need NER here, so we can disable parser and lemmatizer to save time and avoid warnings
                doc = nlp(chunk, disable=["parser", "lemmatizer", "attribute_ruler"])
                ents.extend([
                    (ent.text.strip(), ent.label_, tuple(ent.vector.get()) if hasattr(ent.vector, 'get') else tuple(ent.vector) if ent.vector.size > 0 else None)
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
        item_counts = Counter((text, label) for text, label, vector in ents)
        unique_ents = [(text, label, next((vector for t2, l2, vector in ents if t2 == text and l2 == label), None), count)
                       for (text, label), count in item_counts.items()]

        if config.debug:
            print(f"Unique entities before filtering by count: {len(unique_ents)}")

        # Filter out entities with less than min_count_ner occurrences
        unique_ents = [ent for ent in unique_ents if ent[3] >= min_count_ner]

        if config.debug:
            print(f"Unique entities after filtering by count (min={min_count_ner}): {len(unique_ents)}")

        # Merge entities that contain substrings of other entities
        merged_ents = []
        for ent1 in unique_ents:
            is_substring = False
            for ent2 in unique_ents:
                if ent1[0].lower() != ent2[0].lower() and ent1[0].lower() in ent2[0].lower():
                    is_substring = True
                    break
            if not is_substring:
                merged_ents.append(ent1)

        # Further merging to ensure the longest entity is kept
        final_merged_ents = []
        for ent1 in merged_ents:
            longer_ent_found = False
            for ent2 in merged_ents:
                if ent1[0].lower() != ent2[0].lower() and ent2[0].lower() in ent1[0].lower():
                    longer_ent_found = True
                    break
            if not longer_ent_found:
                final_merged_ents.append(ent1)

        if config.debug:
            print(f"Unique entities after merging: {len(final_merged_ents)}")

        # Find most common words with count > min_count_word and length >= min_word_length
        # Sample first 5 chunks for word counting to save memory
        word_counts = Counter()
        for chunk in text_chunks[:5]:  # Sample first 5 chunks for word counting
            try:
                doc = nlp(chunk, disable=["ner", "parser", "lemmatizer", "attribute_ruler"])
                word_counts.update(
                    token.text for token in doc if token.is_alpha and token.text not in stop_words
                )
                del doc
                gc.collect()
            except:
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

    unique_top_common_words = [word for word in normalized_top_common_words if word.lower() in seen_words]

    result_list = [f"{text} ({label})" for text, label in normalized_final_merged_ents] + unique_top_common_words

    if config.debug:
        print("Finished processing.")
    return '\n'.join(result_list) + '\n'


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
    if config.debug:
        print("Starting cosine similarity matching (GPU)")

    if not text or not vocab:
        if config.debug:
            print("No text or vocabulary to process.")
        return []

    try:
        spacy.prefer_gpu()
        nlp = load_spacy_model(config.nermodel)
        nlp.max_length = 110000
        # For cosine similarity, we only need vectors. Disable everything else to avoid W108 and other warnings.
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"Error loading spaCy model: {e}")
        return []

    orig_values = [entry[lng] for entry in vocab.values() if lng in entry]
    
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
        return []

    # numpy -> cupy (GPU acceleration)
    vocab_matrix = cp.asarray(np.vstack(vocab_vectors))
    vocab_matrix = vocab_matrix / cp.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    matched_words_set = set()

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
    Find vocabulary terms in text using cosine similarity (CPU-only fallback).
    
    Uses NumPy instead of CuPy for systems without GPU.
    Slower but works on any system.
    
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

    try:
        # CPU mode - don't call spacy.prefer_gpu()
        nlp = load_spacy_model(config.nermodel)
        nlp.max_length = 110000
        # For cosine similarity, we only need vectors
        doc = nlp(text, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        if config.debug:
            print(f"Error loading spaCy model: {e}")
        return []

    orig_values = [entry[lng] for entry in vocab.values() if lng in entry]
    
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
        return []

    # NumPy only (CPU) - no CuPy
    vocab_matrix = np.vstack(vocab_vectors)
    vocab_matrix = vocab_matrix / np.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    matched_words_set = set()

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


def create_series_vocab(
    books_folder: str,
    output_file: str = "series.dic",
    min_count_ner: int = 5,
    min_count_word: int = 10,
    min_word_length: int = 5
) -> str:
    """
    Create unified dictionary from all books in folder.
    
    Workflow:
    1. Find all .fb2/.epub/.txt files in folder
    2. For each book: parse text → NER → collect terms
    3. Merge all terms into unified array (aggregate counts)
    4. Filter by min_count criteria
    5. Translate via LLM
    6. Save to JSON .dic file
    
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
    from pathlib import Path
    from collections import Counter
    
    # Find all book files
    supported_exts = {'.fb2', '.epub', '.txt'}
    book_files = []
    for f in os.listdir(books_folder):
        if Path(f).suffix.lower() in supported_exts:
            book_files.append(os.path.join(books_folder, f))
    
    if not book_files:
        raise ValueError(f"No book files found in {books_folder}")
    
    print(f"Found {len(book_files)} books")
    
    # Aggregate terms from all books
    all_entities = []  # [(text, label, book_name), ...]
    all_words = Counter()  # word -> count
    book_names = {}  # book_path -> book_name
    
    for book_path in book_files:
        book_name = Path(book_path).stem
        book_names[book_path] = book_name
        
        print(f"Processing: {book_name}")
        text = extract_text_from_book(book_path)
        
        # Run NER to extract entities
        extracted = make_vocab(
            text,
            min_count_ner=1,  # Lower threshold for aggregation
            min_count_word=1,
            min_word_length=min_word_length
        )
        
        if extracted:
            for line in extracted.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Parse: "Term (CATEGORY)" or just "term"
                match = re.match(r'^(.+?)\s*\(([^)]+)\)$', line)
                if match:
                    term = match.group(1).strip()
                    category = match.group(2).strip()
                    all_entities.append((term, category, book_name))
                else:
                    all_words[line] += 1
    
    # Aggregate entity counts across books
    entity_counts = Counter((term, cat) for term, cat, _ in all_entities)
    
    # Filter by min_count_ner (after aggregation across all books)
    filtered_entities = [
        (term, cat, count) 
        for (term, cat), count in entity_counts.items() 
        if count >= min_count_ner
    ]
    
    # Filter words by min_count_word
    filtered_words = [
        (word, count) 
        for word, count in all_words.items() 
        if count >= min_count_word and len(word) >= min_word_length
    ]
    
    print(f"Filtered entities: {len(filtered_entities)}")
    print(f"Filtered words: {len(filtered_words)}")
    
    # If no terms, return early
    if not filtered_entities and not filtered_words:
        print("No terms found")
        return output_file
    
    # Prepare terms for translation
    terms_for_translation = []
    
    for term, category, count in filtered_entities:
        terms_for_translation.append(term)
    
    for word, count in filtered_words[:100]:  # Limit to top 100 words
        terms_for_translation.append(word)
    
    if not terms_for_translation:
        print("No terms to translate")
        return output_file
    
    print(f"Terms for translation: {len(terms_for_translation)}")
    terms_text = '\n'.join(terms_for_translation)
    
    # Translate via LLM
    from src import utils as ta
    vocab_translated = ta.vocabulary(
        config.source_lang,
        config.target_lang,
        terms_text,
        config.country,
        "Proofread"
    )
    
    # Parse translations
    translations = {}
    for line in vocab_translated.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            parts = line.split('=', 1)
            source = parts[0].strip()
            target = parts[1].strip()
            translations[source.lower()] = target
    
    # Build final vocabulary list in CSV format
    # Format: source = target, category, gender, notes
    
    entity_book_map = {}
    for term, cat, book_name in all_entities:
        key = (term.lower(), cat)
        if key not in entity_book_map:
            entity_book_map[key] = book_name
    
    # Write dictionary in proper CSV format
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Vocabulary for series\n")
        f.write(f"# Format: source = target, category, gender, notes\n")
        f.write(f"# Generated by create_series_vocab\n\n")
        
        # Group by category
        by_category = {}
        for term, category, count in filtered_entities:
            term_lower = term.lower()
            target = translations.get(term_lower, "")
            notes = f"count: {count}"
            if category not in by_category:
                by_category[category] = []
            by_category[category].append((term, target, notes))
        
        # Add words as TERM category
        by_category["TERM"] = []
        for word, count in filtered_words[:100]:
            word_lower = word.lower()
            target = translations.get(word_lower, "")
            notes = f"frequent word (count: {count})"
            by_category["TERM"].append((word, target, notes))
        
        # Write entries grouped by category
        for category, entries in sorted(by_category.items()):
            if not entries:
                continue
            f.write(f"# {category} ({len(entries)} terms)\n")
            for source, target, notes in entries:
                # Format: source = target, category, gender, notes
                f.write(f"{source} = {target}, {category}, , {notes}\n")
            f.write("\n")
    
    print(f"Dictionary saved to: {output_file}")
    return output_file
